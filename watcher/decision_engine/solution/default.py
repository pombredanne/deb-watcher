# -*- encoding: utf-8 -*-
# Copyright (c) 2015 b<>com
#
# Authors: Jean-Emile DARTOIS <jean-emile.dartois@b-com.com>
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
#
from watcher.applier.actions import base as baction
from watcher.common import exception
from watcher.decision_engine.solution import base


class DefaultSolution(base.BaseSolution):
    def __init__(self):
        """Stores a set of actions generated by a strategy

        The DefaultSolution class store a set of actions generated by a
        strategy in order to achieve the goal.
        """
        super(DefaultSolution, self).__init__()
        self._actions = []

    def add_action(self, action_type,
                   input_parameters=None,
                   resource_id=None):

        if input_parameters is not None:
            if baction.BaseAction.RESOURCE_ID in input_parameters.keys():
                raise exception.ReservedWord(name=baction.BaseAction.
                                             RESOURCE_ID)
        if resource_id is not None:
            input_parameters[baction.BaseAction.RESOURCE_ID] = resource_id
        action = {
            'action_type': action_type,
            'input_parameters': input_parameters
        }
        self._actions.append(action)

    def __str__(self):
        return "\n".join(self._actions)

    @property
    def actions(self):
        """Get the current actions of the solution"""
        return self._actions
