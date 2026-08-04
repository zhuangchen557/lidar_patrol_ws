"""Offline example for decoding one or more 13-byte CAN115 return frames."""

from yk_can_sdk import CanStreamParser, decode_feedback


HEX_STREAM = "88 0D EE 01 01 00 00 00 64 FF FF FF 9C"


def main() -> None:
    parser = CanStreamParser()
    for frame in parser.feed(bytes.fromhex(HEX_STREAM)):
        print(frame)
        print(decode_feedback(frame))


if __name__ == "__main__":
    main()

