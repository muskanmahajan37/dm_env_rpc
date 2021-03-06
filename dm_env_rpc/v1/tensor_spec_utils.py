# Copyright 2019 DeepMind Technologies Limited. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or  implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""Helper Python utilities for managing dm_env_rpc TensorSpecs."""

import collections
import numpy as np

from dm_env_rpc.v1 import dm_env_rpc_pb2
from dm_env_rpc.v1 import tensor_utils


Bounds = collections.namedtuple('Bounds', ['min', 'max'])

_SCALAR_VALUE_TYPES = frozenset(
    ('float', 'double', 'int8', 'int32', 'int64', 'uint8', 'uint32', 'uint64'))


def _np_range_info(np_type):
  """Returns type info for `np_type`, which includes min and max attributes."""
  if issubclass(np_type, np.floating):
    return np.finfo(np_type)
  elif issubclass(np_type, np.integer):
    return np.iinfo(np_type)
  else:
    raise ValueError('{} does not have range info.'.format(np_type))


def _get_value(min_max_value, shape, default):
  """Helper function that returns the min/max bounds for a Value message.

  Args:
    min_max_value: Value protobuf message to get value from.
    shape: Optional dimensions to unpack payload data to.
    default: Value to use if min_max_value is not set.

  Returns:
    A scalar if `shape` is empty or None, or an unpacked NumPy array of either
    the unpacked value or provided default.

  """
  which = min_max_value.WhichOneof('payload')
  value = which and getattr(min_max_value, which)

  if value is None:
    min_max = np.broadcast_to(default, shape) if shape else default
  elif which in _SCALAR_VALUE_TYPES:
    min_max = np.broadcast_to(value, shape) if shape else value
  else:
    min_max = tensor_utils.unpack_proto(min_max_value, shape)

  if (shape is not None
      and np.any(np.array(shape) < 0)
      and np.asarray(min_max).size > 1):
    raise ValueError(
        "TensorSpec's with variable length shapes can only have scalar ranges. "
        'Shape: {}, value: {}'.format(shape, min_max))
  return min_max


def bounds(tensor_spec):
  """Gets the inclusive bounds of `tensor_spec`.

  Args:
    tensor_spec: An instance of a dm_env_rpc TensorSpec proto.

  Returns:
    A named tuple (`min`, `max`) of inclusive bounds.

  Raises:
    ValueError: `tensor_spec` does not have a numeric dtype, or the type of its
      `min` or `max` does not match its dtype, or the the bounds are invalid in
      some way.
  """
  np_type = tensor_utils.data_type_to_np_type(tensor_spec.dtype)
  tensor_spec_type = dm_env_rpc_pb2.DataType.Name(tensor_spec.dtype).lower()
  if not issubclass(np_type, np.number):
    raise ValueError('TensorSpec "{}" has non-numeric type {}.'
                     .format(tensor_spec.name, tensor_spec_type))

  min_which = tensor_spec.min.WhichOneof('payload')
  if min_which and not min_which.startswith(tensor_spec_type):
    raise ValueError('TensorSpec "{}" has dtype {} but min type {}.'.format(
        tensor_spec.name, tensor_spec_type, min_which))

  max_which = tensor_spec.max.WhichOneof('payload')
  if max_which and not max_which.startswith(tensor_spec_type):
    raise ValueError('TensorSpec "{}" has dtype {} but max type {}.'.format(
        tensor_spec.name, tensor_spec_type, max_which))

  dtype_bounds = _np_range_info(np_type)
  min_bound = _get_value(tensor_spec.min, tensor_spec.shape, dtype_bounds.min)
  max_bound = _get_value(tensor_spec.max, tensor_spec.shape, dtype_bounds.max)

  if (np.any(min_bound < dtype_bounds.min) or
      np.any(max_bound > dtype_bounds.max)):
    raise ValueError(
        'TensorSpec "{}"\'s bounds [{}, {}] are larger than the bounds on its '
        '{} dtype [{}, {}]'.format(
            tensor_spec.name, min_bound, max_bound, tensor_spec_type,
            dtype_bounds.min, dtype_bounds.max))

  if np.any(max_bound < min_bound):
    raise ValueError('TensorSpec "{}" has min {} larger than max {}.'.format(
        tensor_spec.name, min_bound, max_bound))

  return Bounds(np_type(min_bound), np_type(max_bound))
