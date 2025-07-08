from abc import ABCMeta
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, ClassVar, Self, Sequence

from .Serializable import Serializable, Serializer


class TypeNode[T](Serializer[T], metaclass=ABCMeta): ...


@dataclass(frozen=True)
class StaticLengthNode(TypeNode[int]):
    """StaticLengthNode is a node with a fixed size.

    The size is defined by the size attribute.
    """

    size: int

    def read_from(self, reader, context=None):
        return self.size

    def write_to(self, value, writer, context=None):
        assert value == self.size, f"Expected {self.size} values, got {value} values"
        return 0


@dataclass(frozen=True)
class MemberLengthNode(TypeNode[int]):
    """
    Returns the value of the member with the given name.
    """

    member_name: str

    def _get_member_value(self, context) -> int:
        value = context.get(self.member_name, None)
        assert isinstance(value, int), (
            f"Member {self.member_name} was not an int or did not exist"
        )

        return value

    def read_from(self, reader, context=None):
        assert isinstance(context, dict), "Context was not a dictionary of values"
        return self._get_member_value(context)

    def write_to(self, value, writer, context=None):
        expected_length = self._get_member_value(context)
        assert value == expected_length, (
            f"Expected {expected_length} values, got {value} values"
        )

        return 0


@dataclass(init=False, frozen=True)
class PrimitiveNode[T](TypeNode[T]):
    """Primitive types are directly parsable and mapped to C types.

    U8, U16, U32, U64
    I8, I16, I32, I64
    F16, F32, F64
    """

    size: ClassVar[int]

    def __new__(cls, *args, **kwargs) -> Self:
        if cls in PRIMITIVE_INSTANCE_MAP:
            return PRIMITIVE_INSTANCE_MAP[cls]

        instance = super(PrimitiveNode, cls).__new__(cls, *args, **kwargs)
        PRIMITIVE_INSTANCE_MAP[cls] = instance
        return instance

    def __repr__(self):
        return f"{self.__class__.__name__}"


type PrimitiveInstanceMapType[T] = dict[type[PrimitiveNode[T]], PrimitiveNode[T]]
PRIMITIVE_INSTANCE_MAP: PrimitiveInstanceMapType = {}


class U8Node(PrimitiveNode[int]):
    size = 1

    def read_from(self, reader, context=None):
        return reader.read_u8()

    def write_to(self, value, writer, context=None):
        return writer.write_u8(value)


class U16Node(PrimitiveNode[int]):
    size = 2

    def read_from(self, reader, context=None):
        return reader.read_u16()

    def write_to(self, value, writer, context=None):
        return writer.write_u16(value)


class U32Node(PrimitiveNode[int]):
    size = 4

    def read_from(self, reader, context=None):
        return reader.read_u32()

    def write_to(self, value, writer, context=None):
        return writer.write_u32(value)


class U64Node(PrimitiveNode[int]):
    size = 8

    def read_from(self, reader, context=None):
        return reader.read_u64()

    def write_to(self, value, writer, context=None):
        return writer.write_u64(value)


class I8Node(PrimitiveNode[int]):
    size = 1

    def read_from(self, reader, context=None):
        return reader.read_i8()

    def write_to(self, value, writer, context=None):
        return writer.write_i8(value)


class I16Node(PrimitiveNode[int]):
    size = 2

    def read_from(self, reader, context=None):
        return reader.read_i16()

    def write_to(self, value, writer, context=None):
        return writer.write_i16(value)


class I32Node(PrimitiveNode[int]):
    size = 4

    def read_from(self, reader, context=None):
        return reader.read_i32()

    def write_to(self, value, writer, context=None):
        return writer.write_i32(value)


class I64Node(PrimitiveNode[int]):
    size = 8

    def read_from(self, reader, context=None):
        return reader.read_i64()

    def write_to(self, value, writer, context=None):
        return writer.write_i64(value)


class F16Node(PrimitiveNode[float]):
    size = 2

    def read_from(self, reader, context=None):
        return reader.read_f16()

    def write_to(self, value, writer, context=None):
        return writer.write_f16(value)


class F32Node(PrimitiveNode[float]):
    size = 4

    def read_from(self, reader, context=None):
        return reader.read_f32()

    def write_to(self, value, writer, context=None):
        return writer.write_f32(value)


class F64Node(PrimitiveNode[float]):
    size = 8

    def read_from(self, reader, context=None):
        return reader.read_f64()

    def write_to(self, value, writer, context=None):
        return writer.write_f64(value)


@dataclass(frozen=True)
class StringNode(TypeNode[str]):
    """StringNode is either a length-prefixed string or a C-style string.

    If type_info is None, it is a C-style string.
    If type_info is a TypeNode, it is a length-prefixed string with the given type as the length encoding.
    """

    size_node: TypeNode[int] | None = None
    encoding: str = "utf-8"
    errors: str = "surrogateescape"

    def read_from(self, reader, context=None):
        if self.size_node is None:
            # C-style string
            return reader.read_cstring()
        else:
            # Length-prefixed string
            length = self.size_node.read_from(reader, context)
            return reader.read(length).decode(self.encoding, self.errors)

    def write_to(self, value, writer, context=None):
        if self.size_node is None:
            # C-style string
            return writer.write_string_c(value)
        else:
            # Length-prefixed string
            encoded_value = value.encode(self.encoding, self.errors)
            total_size = self.size_node.write_to(len(encoded_value), writer, context)
            total_size += writer.write(encoded_value)
            return total_size


@dataclass(frozen=True)
class BytesNode(TypeNode[bytes]):
    """BytesNode is a length-prefixed bytes object.

    The first element of type_info is the length encoding type.
    """

    size_node: TypeNode[int]

    def read_from(self, reader, context=None):
        length = self.size_node.read_from(reader, context)
        return reader.read(length)

    def write_to(self, value: bytes, writer, context=None) -> int:
        total_size = self.size_node.write_to(len(value), writer, context)
        total_size += writer.write(value)
        return total_size


@dataclass(frozen=True)
class ListNode[T](TypeNode[list[T]]):
    """ListNode relates to a list of parsable nodes of the same type as type_info encoded with a variable length encoding.

    The first element of type_info is the length encoding type.
    The second element of type_info is the type of the list elements.
    """

    elem_node: TypeNode[T]
    size_node: TypeNode[int]

    def read_from(self, reader, context=None):
        # TODO: change context to be read list fields?
        length = self.size_node.read_from(reader, context)
        return [self.elem_node.read_from(reader, context) for _ in range(length)]

    def write_to(self, value: Sequence[T], writer, context=None) -> int:
        total_size = self.size_node.write_to(len(value), writer, context)
        total_size += sum(
            self.elem_node.write_to(element, writer, context) for element in value
        )
        return total_size


@dataclass(frozen=True)
class TupleNode[T](TypeNode[tuple[T, ...]]):
    """TupleNode relates to a tuple of parsable nodes of different types."""

    nodes: tuple[TypeNode[T], ...]

    def read_from(self, reader, context=None):
        # TODO: change context to be read tuple fields?
        return tuple(node.read_from(reader, context) for node in self.nodes)

    def write_to(self, value: tuple[T, ...], writer, context=None) -> int:
        return sum(
            node.write_to(val, writer, context) for node, val in zip(self.nodes, value)
        )


@dataclass(frozen=True)
class ClassNode[T](TypeNode[T]):
    """ClassNode relates to a class of parsable nodes of different types."""

    nodes: tuple[TypeNode, ...]
    names: tuple[str, ...]
    call: Callable[[dict[str, Any]], T]

    def read_from(self, reader, context=None):
        read_fields = {}
        for name, node in zip(self.names, self.nodes):
            read_fields[name] = node.read_from(reader, read_fields)

        return self.call(read_fields)

    def write_to(self, value: T, writer, context=None):
        return sum(
            node.write_to(getattr(value, name), writer, value)
            for name, node in zip(self.names, self.nodes)
        )


@dataclass(frozen=True)
class StructNode[T: Serializable](TypeNode[T]):
    """StructNode relates to a struct of parsable nodes of different types."""

    clz: type[T]

    def read_from(self, reader, context=None):
        return self.clz.read_from(reader, context)

    def write_to(self, value: T, writer, context=None):
        assert isinstance(value, self.clz), f"Expected {self.clz}, got {type(value)}"
        return self.clz.write_to(value, writer, context)


@dataclass(frozen=True)
class EnumNode[TEnum: Enum, TValue: Serializable](TypeNode[TEnum]):
    """EnumNode relates to an enum of a serializable type."""

    clz: type[TEnum]
    value_node: TypeNode[TValue]

    def read_from(self, reader, context=None):
        return self.clz(self.value_node.read_from(reader, context))

    def write_to(self, value: TEnum, writer, context=None):
        return self.value_node.write_to(value.value, writer, context)


@dataclass(frozen=True)
class ConvertNode[TRaw: Serializable, TValue: Any](TypeNode[TValue]):
    """ConvertNode parses a value of type TRaw and converts it to TValue using the from_raw function.
    For writing, it converts the value to TRaw using the to_raw function.
    """

    raw_node: TypeNode[TRaw]
    from_raw: Callable[[TRaw], TValue]
    to_raw: Callable[[TValue], TRaw]

    def read_from(self, reader, context=None):
        raw = self.raw_node.read_from(reader, context)
        return self.from_raw(raw)

    def write_to(self, value: TValue, writer, context=None):
        raw = self.to_raw(value)
        return self.raw_node.write_to(raw, writer, context)


__all__ = (
    "TypeNode",
    "PrimitiveNode",
    "StringNode",
    "ListNode",
    "TupleNode",
    "ClassNode",
    "StructNode",
    "BytesNode",
    "U8Node",
    "U16Node",
    "U32Node",
    "U64Node",
    "I8Node",
    "I16Node",
    "I32Node",
    "I64Node",
    "F16Node",
    "F32Node",
    "F64Node",
    "EnumNode",
    "ConvertNode",
    "StaticLengthNode",
    "MemberLengthNode",
)
