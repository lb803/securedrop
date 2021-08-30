import json
import subprocess

from flask import session, current_app, abort, g

import typing

import re

from crypto_util import CryptoException
from models import Source

if typing.TYPE_CHECKING:
    from typing import Optional


def was_in_generate_flow() -> bool:
    return 'codenames' in session


def logged_in() -> bool:
    return 'logged_in' in session


def valid_codename(codename: str) -> bool:
    try:
        filesystem_id = current_app.crypto_util.hash_codename(codename)
    except CryptoException as e:
        current_app.logger.info(
                "Could not compute filesystem ID for codename '{}': {}".format(
                    codename, e))
        abort(500)

    source = Source.query.filter_by(filesystem_id=filesystem_id).first()
    return source is not None


def normalize_timestamps(filesystem_id: str) -> None:
    """
    Update the timestamps on all of the source's submissions. This
    minimizes metadata that could be useful to investigators. See
    #301.
    """
    sub_paths = [current_app.storage.path(filesystem_id, submission.filename)
                 for submission in g.source.submissions]
    if len(sub_paths) > 1:
        args = ["touch", "--no-create"]
        args.extend(sub_paths)
        rc = subprocess.call(args)
        if rc != 0:
            current_app.logger.warning(
                "Couldn't normalize submission "
                "timestamps (touch exited with %d)" %
                rc)


def check_url_file(path: str, regexp: str) -> 'Optional[str]':
    """
    Check that a file exists at the path given and contains a single line
    matching the regexp. Used for checking the source interface address
    files in /var/lib/securedrop (as the Apache user can't read Tor config)
    """
    try:
        f = open(path, "r")
        contents = f.readline().strip()
        f.close()
        if re.match(regexp, contents):
            return contents
        else:
            return None
    except IOError:
        return None


def get_sourcev3_url() -> 'Optional[str]':
    return check_url_file("/var/lib/securedrop/source_v3_url",
                          r"^[a-z0-9]{56}\.onion$")


def fit_codenames_into_cookie(codenames: dict) -> dict:
    """
    If `codenames` will approach `werkzeug.Response.max_cookie_size` once
    serialized, incrementally pop off the oldest codename until the remaining
    (newer) ones will fit.
    """

    serialized = json.dumps(codenames).encode()
    if len(codenames) > 1 and len(serialized) > 4000:  # werkzeug.Response.max_cookie_size = 4093
        if current_app:
            current_app.logger.warn(f"Popping oldest of {len(codenames)} "
                                    f"codenames ({len(serialized)} bytes) to "
                                    f"fit within maximum cookie size")
        del codenames[list(codenames)[0]]  # FIFO

        return fit_codenames_into_cookie(codenames)

    return codenames
