from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, replace
from inspect import isclass
from typing import (
    Annotated,
    Any,
    Literal,
    Protocol,
    Self,
    get_args,
)

from ._typing_helpers import get_origin_type
from .TypeNode import StaticLengthNode, MemberLengthNode, TypeNode, U32Node


@dataclass(frozen=True)
class BinarySerializableOptions:
    length_type: TypeNode[int] = U32Node()

    def update_by_type(self, option_type: Any) -> Self:
        arguments = get_args(option_type)
        origin = get_origin_type(option_type)

        if origin is Annotated:
            origin = arguments[0]

        assert issubclass(origin, BinarySerializableOption)
        return origin.apply_option(self, option_type)


class BinarySerializableOption(metaclass=ABCMeta):
    @classmethod
    @abstractmethod
    def apply_option[T: BinarySerializableOptions](
        cls, options: T, option_type: Any
    ) -> T: ...


type member[TType] = TType  # TODO: Implement member-only serialization behavior
"""
Used for defining the members to serialize when not all class members should be serialized.
"""

type custom[TType, *TOptions] = Annotated[TType, *TOptions]
"""
Used for overriding type-level serialization settings for a given member.
"""


class length_provider(BinarySerializableOption):
    @classmethod
    def _parse_prefixed_length(
        cls, option_type: type["prefixed_length"]
    ) -> TypeNode[int]:
        args = get_args(option_type)
        assert len(args) == 1, "prefixed_length must have one argument"

        val = args[0]

        annotated_args = get_args(val)
        assert len(annotated_args) == 2, "Annotated type node must have two arguments"
        annotated_type, annotated_node = annotated_args

        if isclass(annotated_node):
            if issubclass(annotated_node, TypeNode):
                return annotated_node()
            else:
                raise ValueError(
                    f"Length type must be a TypeNode[int] or an instance of it, got {annotated_node} instead."
                )

        if isinstance(annotated_node, TypeNode):
            return annotated_node

        raise RuntimeError(f"Invalid length type: {annotated_node}")

    @classmethod
    def _parse_annotated_length(cls, option_type: type[Annotated]) -> TypeNode[int]:
        args = get_args(option_type)
        assert len(args) == 2, "Annotated length type must have two arguments"

        option_type, val = args
        if get_origin_type(val) is Literal:
            val_args = get_args(val)
            assert len(val_args) == 1, "Length type must be a Literal with one argument"

            literal_value = val_args[0]
            if isinstance(literal_value, int):
                return StaticLengthNode(literal_value)

            if isinstance(literal_value, str):
                return MemberLengthNode(literal_value)

            raise ValueError(
                f"Length type literal must either be an int or a string, got {type(literal_value)} instead."
            )

        raise ValueError(f"Invalid length type: {val}")

    @classmethod
    def apply_option(
        cls, options: BinarySerializableOptions, option_type: Any
    ) -> BinarySerializableOptions:
        origin_type = get_origin_type(option_type)
        type_node = (
            cls._parse_prefixed_length(option_type)
            if origin_type is prefixed_length
            else cls._parse_annotated_length(option_type)
        )

        return replace(options, length_type=type_node)


class prefixed_length[T: int | TypeNode[int]](length_provider):
    """
    Used for specifying the prefixed length type for a variable-length array.
    Must be serializing an int type.
    """

    pass


class static_length:
    """
    Used for specifying the size for an constant-sized array.
    """

    def __class_getitem__(cls, item: int):
        return Annotated[length_provider, Literal[item]]


class member_length:
    """
    Used for specifying the member that provides the size for a variable-sized array.
    Member must be an int type.
    """

    def __class_getitem__(cls, item: str):
        return Annotated[length_provider, Literal[item]]


class Converter[TValue, TRaw](Protocol):
    @staticmethod
    def from_raw(raw: TRaw) -> TValue: ...

    @staticmethod
    def to_raw(value: TValue) -> TRaw: ...


type convert[TValue, TRaw, TConverter: Converter] = Annotated[
    TValue, Converter[TValue, TRaw], TConverter
]
"""
Used for directly converting a value to/from a different type when serializing and deserializing.
"""
# pyright complains about Callable | None, but Union seems to be fine????

__all__ = (
    "member",
    "convert",
    "custom",
    "BinarySerializableOptions",
    # length options
    "prefixed_length",
    "static_length",
    "member_length",
)
