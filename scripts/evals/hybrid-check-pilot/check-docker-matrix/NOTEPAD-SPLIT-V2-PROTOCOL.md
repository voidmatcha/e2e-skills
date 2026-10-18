<!-- SPDX-License-Identifier: Apache-2.0 -->
# Notepad split host archive compatibility correction

The first attempt stopped before any Docker app or browser run because host
Python 3.9 rejects `tarfile.extractall(filter='data')`. Its preflight,
failure and frozen runner bytes remain under `notepad-split-v1/`; no cell is
valid. V2 changes only archive extraction: iterate the already pinned Git
archive, accept relative regular files and directories without traversal,
reject other member kinds, and write each file into the fresh cell. The
app, fault, test, oracle, images, seven-cell order and acceptance criteria in
`NOTEPAD-SPLIT-PROTOCOL.md` remain fixed. Run V2 in a new output directory;
stop at its first invalid cell and preserve it.
