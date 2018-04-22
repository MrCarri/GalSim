# Copyright (c) 2012-2018 by the GalSim developers team on GitHub
# https://github.com/GalSim-developers
#
# This file is part of GalSim: The modular galaxy image simulation toolkit.
# https://github.com/GalSim-developers/GalSim
#
# GalSim is free software: redistribution and use in source and binary forms,
# with or without modification, are permitted provided that the following
# conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions, and the disclaimer given in the accompanying LICENSE
#    file.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions, and the disclaimer given in the documentation
#    and/or other materials provided with the distribution.
#

# Define the class hierarchy for errors and warnings emitted by GalSim that aren't
# obviously one of the standard python errors.

# Base class for all GalSim-emitted run-time errors.
class GalSimError(RuntimeError):
    pass


# Base class for all GalSim-emitted warnings.
class GalSimWarning(UserWarning):
    pass

