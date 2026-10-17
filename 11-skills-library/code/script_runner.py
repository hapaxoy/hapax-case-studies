"""Runs one library script with its DuckDB connections locked down. Used by harness.ToolBox.run_script only.

    python -I script_runner.py <script.py> <script arguments...>

The library's scripts (fiscal.py, query_check.py) open the warehouse themselves, and query_check.py will run any SQL it is
given with --sql or --file. Without this wrapper a model could pass it a query such as SELECT * FROM read_text('...') and
read files the run is not meant to see. So every connection a script opens through duckdb.connect gets the same two
settings as the run_sql tool: external access off (no file can be read, written or attached) and the configuration
locked (the setting cannot be switched back on). The script file itself is run unchanged with runpy.
"""
import runpy
import sys

import duckdb

_real_connect = duckdb.connect


def locked_connect(*args, **kwargs):
    connection = _real_connect(*args, **kwargs)
    connection.execute("SET enable_external_access=false")
    connection.execute("SET lock_configuration=true")
    return connection


duckdb.connect = locked_connect

if len(sys.argv) < 2:
    sys.exit("script_runner.py needs a script path")
script_path = sys.argv[1]
sys.argv = [script_path] + sys.argv[2:]
runpy.run_path(script_path, run_name="__main__")
