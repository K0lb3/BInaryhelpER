from enum import Enum, IntEnum, IntFlag, StrEnum
from functools import cache
from inspect import isclass
from types import get_original_bases
from typing import (
    Annotated,
    Any,
    Self,
    get_args,
    get_type_hints,
    ClassVar,
)

from ._typing_helpers import get_origin_type, resolve_genericalias
from .builtins import (
    cstr,
    f16,
    f32,
    f64,
    i8,
    i16,
    i32,
    i64,
    u8,
    u16,
    u32,
    u64,
)
from .options import BinarySerializableOptions, convert, custom, member
from .Serializable import Serializable
from .TypeNode import (
    BytesNode,
    ClassNode,
    ConvertNode,
    EnumNode,
    ListNode,
    StringNode,
    StructNode,
    TupleNode,
    TypeNode,
)

PRIMITIVES = (
    u8,
    u16,
    u32,
    u64,
    i8,
    i16,
    i32,
    i64,
    f16,
    f32,
    f64,
)


class BinarySerializable[*TOptions](Serializable):
    @classmethod
    def _get_node(cls) -> ClassNode[Self]:
        return build_type_node(cls)

    @classmethod
    def from_dict(cls, parsed_dict: dict[str, Any]) -> Self:
        return cls(**parsed_dict)

    @classmethod
    def read_from(cls, reader, context=None):
        return cls._get_node().read_from(reader, context)

    def write_to(self, writer, context=None):
        return self._get_node().write_to(self, writer, context)


def get_binary_serializable_spec(cls: type[BinarySerializable]) -> Any:
    for base in get_original_bases(cls):
        if get_origin_type(base) is BinarySerializable:
            return base

    raise ValueError(f"Type {cls} does not inherit from BinarySerializable")


def parse_enum_base_type(clz: type[Enum]) -> type:
    for enum_spec, value_type in [(StrEnum, str), (IntEnum, int), (IntFlag, int)]:
        if issubclass(clz, enum_spec):
            return value_type

    bases = get_original_bases(clz)
    assert len(bases) == 2, "enum member must have two arguments"
    assert bases[1] is Enum, "enum second base type must be Enum"
    return bases[0]


def parse_annotation(annotation: Any, options: BinarySerializableOptions) -> TypeNode:
    if annotation in PRIMITIVES:
        args = get_args(annotation)
        assert len(args) >= 2 and issubclass(args[1], TypeNode), (
            f"Invalid primitive {annotation}"
        )
        return args[1]()

    origin = get_origin_type(annotation)
    args = get_args(annotation)

    if annotation is cstr:
        return StringNode()

    if annotation is str:
        return StringNode(options.length_type)

    if origin is bytes:
        return BytesNode(options.length_type)

    if origin is list:
        assert len(args) == 1, "list must have one argument"
        elem_node = parse_annotation(
            annotation=args[0],
            options=options,
        )
        return ListNode(elem_node, options.length_type)

    if origin is tuple:
        return TupleNode(
            tuple(parse_annotation(annotation=arg, options=options) for arg in args)
        )

    if origin is custom:
        assert len(args) >= 1, "member must have at least one argument"
        member_type = args[0]
        member_options = options
        for option in args[1:]:
            member_options = member_options.update_by_type(option)

        return parse_annotation(member_type, member_options)

    if origin is member:
        assert len(args) == 1, "member must have one argument"
        return parse_annotation(args[0], options)

    if origin is convert:
        assert len(args) == 3, "convert must have three arguments"
        value_type, raw_type, converter = args
        raw_node = parse_annotation(raw_type, options)
        return ConvertNode(raw_node, converter.from_raw, converter.to_raw)

    if origin is Annotated:
        for arg in args:
            if isinstance(arg, TypeNode):
                return arg
            elif issubclass(arg, TypeNode):
                return arg()
            elif issubclass(arg, BinarySerializable):
                return StructNode(clz=arg)

    if isclass(annotation):
        if issubclass(annotation, Serializable):
            return StructNode(clz=annotation)

        if issubclass(annotation, Enum):
            value_type = parse_enum_base_type(annotation)
            return EnumNode(annotation, parse_annotation(value_type, options))

    if (
        hasattr(annotation, "__value__")
        and get_origin_type(annotation.__value__) is custom
    ):
        return parse_annotation(
            resolve_genericalias(origin, args),
            options=options,
        )

    raise NotImplementedError(
        f"Unsupported annotation: {annotation}. "
        f"Please use a type from the bier.struct module."
    )


def get_serialization_options(
    arguments: tuple[Any, ...], current_options: BinarySerializableOptions
) -> BinarySerializableOptions:
    if len(arguments) == 0:
        return current_options

    options = current_options
    for argument in arguments:
        options = options.update_by_type(argument)

    return options


def get_type_serialization_options(cls: type[BinarySerializable]):
    spec = get_binary_serializable_spec(cls)
    arguments = get_args(spec)
    return get_serialization_options(arguments, BinarySerializableOptions())


@cache
def build_type_node[T: BinarySerializable](cls: type[T]) -> ClassNode[T]:
    # get default options from the class
    serialization_options = get_type_serialization_options(cls)

    # get all member type hints
    type_hints = get_type_hints(cls, include_extras=True)

    # filter out class var members
    type_hints = {
        name: value
        for name, value in type_hints.items()
        if get_origin_type(value) is not ClassVar
    }

    names = tuple(type_hints.keys())
    nodes = tuple(
        parse_annotation(annotation, serialization_options)
        for annotation in type_hints.values()
    )

    return ClassNode(
        names=names,
        nodes=nodes,
        call=cls.from_dict,
    )


__all__ = ("BinarySerializable",)
