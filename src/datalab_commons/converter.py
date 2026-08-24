def to_snake_case(camel_string: str, *, treat_digits_as_capitals: bool = False) -> str:
    def check_character(c: str) -> str:
        if c.isupper() or (treat_digits_as_capitals and c.isdigit()):
            return f"_{c}"
        else:
            return c

    return "".join(check_character(c) for c in camel_string).lstrip("_").lower()
