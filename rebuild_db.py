"""
Placeholder for the database rebuild utility (see TODO).

The intent is to walk an existing PUBLIC_DIR and recreate the `endpoints` rows for the
files found there, to recover an install whose main.db was lost while its uploads
survived. The managed tree needs no such recovery, `utils.paths.reload_managed_tree`
already rebuilds it from disk on every start; only the short random endpoints, whose
mapping to a file exists solely in the database, would have to be reconstructed here.

Not implemented yet.
"""
