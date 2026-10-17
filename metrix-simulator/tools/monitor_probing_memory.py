#!/usr/bin/env python3
"""Run Metrix and sample its RSS at each variable probing message.

The child writes to a pseudo-terminal so its progress messages are delivered
promptly. This samples resident memory; only an ASan build can report leaks.
"""

import argparse
from datetime import datetime
import errno
import os
from pathlib import Path
import pty
import re
import subprocess
import sys


SIMULATOR = Path(__file__).resolve().parents[1]
PROBING = re.compile(rb"Iteration de variable probing 1(?!\d)", re.IGNORECASE)


def read_variant_metadata(path):
    with path.open("rb") as source:
        fields = source.readline().strip().split(b";")
        if len(fields) < 2 or fields[0] != b"NT":
            raise ValueError(f"Unable to read variant count from {path}: expected NT;<count>;")
        count = int(fields[1])
        if count < 1:
            raise ValueError(f"Invalid variant count in {path}: {count}")
        # Negative IDs describe changes to the base network. The first
        # nonnegative ID is the first variant accepted by Metrix.
        for line in source:
            identifier = line.partition(b";")[0].strip()
            if identifier.isdigit():
                return count, int(identifier)
    raise ValueError(f"No numbered variant found in {path}")


def result_contains_fatal_error(path):
    try:
        with path.open("rb") as result:
            result.seek(0, os.SEEK_END)
            result.seek(max(0, result.tell() - 65536))
            return b"Not recoverable error:" in result.read()
    except FileNotFoundError:
        return False


def memory_kib(pid):
    try:
        status = Path(f"/proc/{pid}/status").read_text()
    except FileNotFoundError:
        return None
    values = {name: int(amount) for name, amount in re.findall(
        r"^(VmRSS|VmHWM):\s+(\d+)\s+kB", status, re.MULTILINE)}
    if "VmRSS" not in values or "VmHWM" not in values:
        return None
    return values["VmRSS"], values["VmHWM"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path, help="directory containing fort.json and variantes.csv")
    parser.add_argument("--build-dir", type=Path, default=Path("build-asan"),
                        help="build directory under metrix-simulator (default: build-asan; use build for the regular binary)")
    parser.add_argument("--binary", type=Path, help="explicit binary path; overrides --build-dir")
    parser.add_argument("--variant-file", default="variantes.csv")
    parser.add_argument("--variants", type=int, help="override the NT count in the variant file")
    parser.add_argument("--first-variant", type=int,
                        help="override the first numbered variant found in the file")
    parser.add_argument("--samples", type=Path, help="TSV output (default: input_dir/rss-probing.tsv)")
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    build_dir = args.build_dir if args.build_dir.is_absolute() else SIMULATOR / args.build_dir
    binary = args.binary.resolve() if args.binary else build_dir / "metrix-simulator"
    variant_file = input_dir / args.variant_file
    samples = args.samples.resolve() if args.samples else input_dir / "rss-probing.tsv"
    if not input_dir.is_dir():
        parser.error(f"Input directory does not exist: {input_dir}")
    if not binary.is_file() or not os.access(binary, os.X_OK):
        parser.error(f"Binary is missing or not executable: {binary}")
    if not variant_file.is_file():
        parser.error(f"Variant file does not exist: {variant_file}")
    try:
        file_count, file_first = read_variant_metadata(variant_file)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    variants = args.variants if args.variants is not None else file_count
    first_variant = args.first_variant if args.first_variant is not None else file_first
    if variants < 1 or first_variant < 0:
        parser.error("--variants must be positive and --first-variant must be nonnegative")

    env = os.environ.copy()
    if "asan" in binary.parent.name.lower():
        existing_asan = env.get("ASAN_OPTIONS", "")
        env["ASAN_OPTIONS"] = f"{existing_asan}:detect_leaks=1" if existing_asan else "detect_leaks=1"
    env["HADES_DIR"] = "."
    env["METRIX_ETC"] = str(SIMULATOR / "etc")
    command = [str(binary), "metrixOut.txt", str(variant_file), "out",
               str(first_variant), str(variants)]

    # Fail before launching a potentially hours-long run if the sample file cannot be written.
    with samples.open("w", encoding="utf-8") as output:
        output.write("timestamp\toccurrence\tVmRSS_KiB\tVmHWM_KiB\n")

    print(f"Binary: {binary}; running {variants} variants starting at ID {first_variant}; "
          f"samples: {samples}",
          file=sys.stderr, flush=True)
    master, slave = pty.openpty()
    try:
        process = subprocess.Popen(command, cwd=input_dir, env=env, stdin=subprocess.DEVNULL,
                                   stdout=slave, stderr=slave)
    finally:
        os.close(slave)
    pending = b""
    occurrence = 0
    fatal_error = False
    try:
        with samples.open("a", encoding="utf-8") as output:
            while True:
                try:
                    chunk = os.read(master, 4096)
                except OSError as error:
                    if error.errno == errno.EIO:  # Linux PTY closes with EIO after child exit.
                        break
                    raise
                if not chunk:
                    break
                os.write(sys.stdout.fileno(), chunk)
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    if b"Not recoverable error:" in line:
                        fatal_error = True
                    if not PROBING.search(line):
                        continue
                    occurrence += 1
                    values = memory_kib(process.pid)
                    if values is None:
                        print("[memory] Process ended before RSS could be sampled", file=sys.stderr)
                        continue
                    rss, peak = values
                    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
                    output.write(f"{timestamp}\t{occurrence}\t{rss}\t{peak}\n")
                    output.flush()
                    print(f"[memory #{occurrence}] RSS {rss / 1024:.1f} MiB, "
                          f"peak {peak / 1024:.1f} MiB", file=sys.stderr, flush=True)
    except KeyboardInterrupt:
        if process.poll() is None:
            process.terminate()
        return 130
    finally:
        os.close(master)
        process.wait()
    if fatal_error or result_contains_fatal_error(input_dir / "metrixOut.txt"):
        print("Metrix stopped with a nonrecoverable error; see its output above.", file=sys.stderr)
        return 1
    if occurrence == 0 and process.returncode == 0:
        print("No probing iteration was reached; check metrixOut.txt for an early stop.", file=sys.stderr)
        return 1
    return process.returncode


if __name__ == "__main__":
    sys.exit(main())
