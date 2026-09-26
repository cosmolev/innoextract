# decompiler.com build

This fork's `decompiler` branch starts at upstream PR #210 commit
`376a13e7c41cc5528b6088d0dd16ec1b323a8d37` from `dscho/innoextract`.
It contains local changes to Daniel Scharrer's innoextract; the upstream ZLIB
license and attribution are preserved. The first commit fixes unused verification
hashes and rejects unsupported/corrupt encryption headers. The next commit adds
the stdout adapter and native regression tests.

## Build and test

Dependencies: a C++ compiler, CMake, Boost, xz/liblzma, and Python 3.

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DUSE_LTO=OFF \
  -DBUILD_TESTS=ON -DBUILD_DECRYPTION=OFF
cmake --build build -j2
ctest --test-dir build --output-on-failure
bash tests/decompiler/run.sh "$PWD/build/innoextract"
```

The runner downloads three public installers, verifies their SHA-256 hashes,
checks full extraction streams and runs six malformed-input/CLI regression tests.
It never executes an installer. Git x64 covers the PR's unused-hash regression.
`verify_inno.py` also accepts a larger corpus and `--reference` for byte-for-byte
comparison with a previous streaming decoder; `--baseline` checks an unmodified
upstream executable using its filesystem-free `--test` action.

The original matrix passed 19 public installers, including Inno releases 6.2.2,
6.3.3, 6.4.x, 6.5.x, 6.6.x, 6.7.x, 7.0.2, 7.1.0 and both Git architectures.
Embedded setup-data versions differ from package versions. The integration repo
`cosmolev/decompiler` records input/output hashes and application/STG test results.

## Stdout protocol

`--decompiler-stream --silent --no-extract-unknown --no-gog-galaxy --collisions error`
emits `IEX1\n`, followed by records containing:

1. Decimal alias count and uncompressed byte length, each followed by a newline.
2. For each alias, decimal UTF-8 name byte length plus newline, then the name bytes.
3. Exactly the declared payload bytes, followed by `OK!\n` only after checksum checks.

Records share one data payload across aliases. EOF after a complete record is the
end of the stream; the caller must also check the process exit code. Diagnostics
use stderr. A nonzero exit can follow earlier valid records; an unfinished record
must never be published. There is no global success trailer.

Stream mode never passes member names to the native filesystem writer. Its caller
must validate paths, enforce entry/byte/time limits, and publish a record only after
its success trailer. Checks include payload digests and member digests when defined
by the format. An unused `FileVerificationNone` hash is not a SHA-256 digest.
The stream is integrity checked, not an assertion of publisher signature authenticity.
Encrypted installers, external data slices, multipart members and conflicting
filesystem/output actions are refused. Decryption is disabled in our build.

## Updating the integration

Keep `master` as the upstream tracking branch and use `decompiler` for custom commits.
Review/merge upstream changes, rerun the corpus and failure tests, and pin the resulting
full commit plus source-archive SHA-256 in decompiler's install script. Do not deploy
a mutable branch name or keep a second copy of the source patch in the integration repo.
The installation `.version` file records the exact fork commit and archive checksum.
