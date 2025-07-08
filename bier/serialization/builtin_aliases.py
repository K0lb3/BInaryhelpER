from .options import custom, length_provider

# useful aliases

type list_d[TType, LType: length_provider] = custom[list[TType], LType]
type str_d[T: length_provider] = custom[str, T]
type bytes_d[T: length_provider] = custom[bytes, T]

__all__ = (
    # type aliases
    "list_d",
    "str_d",
    "bytes_d",
)
