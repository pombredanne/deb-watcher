# -*- encoding: utf-8 -*-
# Copyright (c) 2015 b<>com
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import mock

from watcher.common import utils
from watcher.db import api as db_api
from watcher.decision_engine.planner import default as pbase
from watcher.decision_engine.solution import default as dsol
from watcher.decision_engine.strategy import strategies
from watcher import objects
from watcher.tests.db import base
from watcher.tests.db import utils as db_utils
from watcher.tests.decision_engine.model import faker_cluster_state
from watcher.tests.decision_engine.model import faker_metrics_collector as fake
from watcher.tests.objects import utils as obj_utils


class SolutionFaker(object):
    @staticmethod
    def build():
        metrics = fake.FakerMetricsCollector()
        current_state_cluster = faker_cluster_state.FakerModelCollector()
        sercon = strategies.BasicConsolidation(config=mock.Mock())
        sercon._compute_model = current_state_cluster.generate_scenario_1()
        sercon.ceilometer = mock.MagicMock(
            get_statistics=metrics.mock_get_statistics)
        return sercon.execute()


class SolutionFakerSingleHyp(object):
    @staticmethod
    def build():
        metrics = fake.FakerMetricsCollector()
        current_state_cluster = faker_cluster_state.FakerModelCollector()
        sercon = strategies.BasicConsolidation(config=mock.Mock())
        sercon._compute_model = (
            current_state_cluster.generate_scenario_3_with_2_nodes())
        sercon.ceilometer = mock.MagicMock(
            get_statistics=metrics.mock_get_statistics)

        return sercon.execute()


class TestActionScheduling(base.DbTestCase):

    def setUp(self):
        super(TestActionScheduling, self).setUp()
        self.strategy = db_utils.create_test_strategy(name="dummy")
        self.audit = db_utils.create_test_audit(
            uuid=utils.generate_uuid(), strategy_id=self.strategy.id)
        self.default_planner = pbase.DefaultPlanner(mock.Mock())

    def test_schedule_actions(self):
        solution = dsol.DefaultSolution(
            goal=mock.Mock(), strategy=self.strategy)

        parameters = {
            "source_node": "server1",
            "destination_node": "server2",
        }
        solution.add_action(action_type="migrate",
                            resource_id="b199db0c-1408-4d52-b5a5-5ca14de0ff36",
                            input_parameters=parameters)

        with mock.patch.object(
            pbase.DefaultPlanner, "create_action",
            wraps=self.default_planner.create_action
        ) as m_create_action:
            self.default_planner.config.weights = {'migrate': 3}
            action_plan = self.default_planner.schedule(
                self.context, self.audit.id, solution)

        self.assertIsNotNone(action_plan.uuid)
        self.assertEqual(1, m_create_action.call_count)
        filters = {'action_plan_id': action_plan.id}
        actions = objects.Action.dbapi.get_action_list(self.context, filters)
        self.assertEqual("migrate", actions[0].action_type)

    def test_schedule_two_actions(self):
        solution = dsol.DefaultSolution(
            goal=mock.Mock(), strategy=self.strategy)

        parameters = {
            "source_node": "server1",
            "destination_node": "server2",
        }
        solution.add_action(action_type="migrate",
                            resource_id="b199db0c-1408-4d52-b5a5-5ca14de0ff36",
                            input_parameters=parameters)

        solution.add_action(action_type="nop",
                            resource_id="",
                            input_parameters={})

        with mock.patch.object(
            pbase.DefaultPlanner, "create_action",
            wraps=self.default_planner.create_action
        ) as m_create_action:
            self.default_planner.config.weights = {'migrate': 3, 'nop': 0}
            action_plan = self.default_planner.schedule(
                self.context, self.audit.id, solution)
        self.assertIsNotNone(action_plan.uuid)
        self.assertEqual(2, m_create_action.call_count)
        # check order
        filters = {'action_plan_id': action_plan.id}
        actions = objects.Action.dbapi.get_action_list(self.context, filters)
        self.assertEqual("nop", actions[0].action_type)
        self.assertEqual("migrate", actions[1].action_type)

    def test_schedule_actions_with_unknown_action(self):
        solution = dsol.DefaultSolution(
            goal=mock.Mock(), strategy=self.strategy)

        parameters = {
            "src_uuid_node": "server1",
            "dst_uuid_node": "server2",
        }
        solution.add_action(action_type="migrate",
                            resource_id="b199db0c-1408-4d52-b5a5-5ca14de0ff36",
                            input_parameters=parameters)

        solution.add_action(action_type="new_action_type",
                            resource_id="",
                            input_parameters={})

        with mock.patch.object(
            pbase.DefaultPlanner, "create_action",
            wraps=self.default_planner.create_action
        ) as m_create_action:
            self.default_planner.config.weights = {'migrate': 0}
            self.assertRaises(KeyError, self.default_planner.schedule,
                              self.context, self.audit.id, solution)
        self.assertEqual(2, m_create_action.call_count)


class TestDefaultPlanner(base.DbTestCase):

    def setUp(self):
        super(TestDefaultPlanner, self).setUp()
        self.default_planner = pbase.DefaultPlanner(mock.Mock())
        self.default_planner.config.weights = {
            'nop': 0,
            'sleep': 1,
            'change_nova_service_state': 2,
            'migrate': 3
        }

        self.goal = obj_utils.create_test_goal(self.context)
        self.strategy = obj_utils.create_test_strategy(
            self.context, goal_id=self.goal.id)
        obj_utils.create_test_audit_template(
            self.context, goal_id=self.goal.id, strategy_id=self.strategy.id)

        p = mock.patch.object(db_api.BaseConnection, 'create_action_plan')
        self.mock_create_action_plan = p.start()
        self.mock_create_action_plan.side_effect = (
            self._simulate_action_plan_create)
        self.addCleanup(p.stop)

        q = mock.patch.object(db_api.BaseConnection, 'create_action')
        self.mock_create_action = q.start()
        self.mock_create_action.side_effect = (
            self._simulate_action_create)
        self.addCleanup(q.stop)

    def _simulate_action_plan_create(self, action_plan):
        action_plan.create()
        return action_plan

    def _simulate_action_create(self, action):
        action.create()
        return action

    @mock.patch.object(objects.Strategy, 'get_by_name')
    def test_schedule_scheduled_empty(self, m_get_by_name):
        m_get_by_name.return_value = self.strategy
        audit = db_utils.create_test_audit(
            goal_id=self.goal.id, strategy_id=self.strategy.id)
        fake_solution = SolutionFakerSingleHyp.build()
        action_plan = self.default_planner.schedule(self.context,
                                                    audit.id, fake_solution)
        self.assertIsNotNone(action_plan.uuid)

    @mock.patch.object(objects.Strategy, 'get_by_name')
    def test_scheduler_warning_empty_action_plan(self, m_get_by_name):
        m_get_by_name.return_value = self.strategy
        audit = db_utils.create_test_audit(
            goal_id=self.goal.id, strategy_id=self.strategy.id)
        fake_solution = SolutionFaker.build()
        action_plan = self.default_planner.schedule(
            self.context, audit.id, fake_solution)
        self.assertIsNotNone(action_plan.uuid)
