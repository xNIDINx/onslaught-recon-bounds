# -*- coding: utf-8 -*-

from __future__ import print_function

import os
import sys
import zipfile


def main():
    if len(sys.argv) < 4:
        raise SystemExit('usage: package_mtmod.py <root> <output> <relative-file> [...]')

    root = os.path.abspath(sys.argv[1])
    output = os.path.abspath(sys.argv[2])
    relative_files = sys.argv[3:]

    archive = zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED)
    try:
        for relative_path in relative_files:
            archive_name = relative_path.replace('\\', '/')
            source_path = os.path.abspath(os.path.join(root, *archive_name.split('/')))
            if not source_path.startswith(root + os.sep):
                raise RuntimeError('file is outside package root: %s' % relative_path)
            if not os.path.isfile(source_path):
                raise RuntimeError('package file is missing: %s' % source_path)
            archive.write(source_path, archive_name)
    finally:
        archive.close()

    archive = zipfile.ZipFile(output, 'r')
    try:
        entries = archive.infolist()
        if len(entries) != len(relative_files):
            raise RuntimeError('unexpected archive entry count')
        for entry in entries:
            if entry.compress_type != zipfile.ZIP_STORED:
                raise RuntimeError('compressed entry is not supported by the client: %s' % entry.filename)
    finally:
        archive.close()

    print('Created %s with %d stored files' % (output, len(relative_files)))


if __name__ == '__main__':
    main()
