__version__ = "0.0.1"
AUTHOR = "Vanessa Sochat"
AUTHOR_EMAIL = "vsoch@users.noreply.github.com"
NAME = "fractale"
PACKAGE_URL = "https://github.com/compspec/fractale"
KEYWORDS = "cluster, orchestration, transformer, jobspec, flux"
DESCRIPTION = "Jobspec specification and translation layer for cluster work"
LICENSE = "LICENSE"


################################################################################
# Global requirements

# Note that the spack / environment modules plugins are installed automatically.
# This doesn't need to be the case.
INSTALL_REQUIRES = (
    ("jsonschema", {"min_version": None}),
    ("compspec", {"min_version": None}),
    ("compspec-spack", {"min_version": None}),
    ("compspec-modules", {"min_version": None}),
    # Yeah, probably overkill, just being used for printing the scripts
    ("rich", {"min_version": None}),
)

TESTS_REQUIRES = (("pytest", {"min_version": "4.6.2"}),)
INSTALL_REQUIRES_ALL = INSTALL_REQUIRES + TESTS_REQUIRES
