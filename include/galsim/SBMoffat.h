/* -*- c++ -*-
 * Copyright (c) 2012-2014 by the GalSim developers team on GitHub
 * https://github.com/GalSim-developers
 *
 * This file is part of GalSim: The modular galaxy image simulation toolkit.
 * https://github.com/GalSim-developers/GalSim
 *
 * GalSim is free software: redistribution and use in source and binary forms,
 * with or without modification, are permitted provided that the following
 * conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice, this
 *    list of conditions, and the disclaimer given in the accompanying LICENSE
 *    file.
 * 2. Redistributions in binary form must reproduce the above copyright notice,
 *    this list of conditions, and the disclaimer given in the documentation
 *    and/or other materials provided with the distribution.
 */

#ifndef SBMOFFAT_H
#define SBMOFFAT_H
/** 
 * @file SBMoffat.h @brief SBProfile that implements a Moffat profile.
 */

#include "SBProfile.h"

namespace galsim {

    /**
     * @brief Surface Brightness for the Moffat Profile (an approximate description of ground-based
     * PSFs).
     *
     * The Moffat surface brightness profile is I(R) propto [1 + (r/r_scale)^2]^(-beta).  The
     * SBProfile representation of a Moffat profile also includes an optional truncation beyond a
     * given radius.
     */
    class SBMoffat : public SBProfile 
    {
    public:
        enum  RadiusType
        {
            FWHM,
            HALF_LIGHT_RADIUS,
            SCALE_RADIUS
        };

        /** @brief Constructor.
         *
         * @param[in] beta           Moffat beta parameter for profile `[1 + (r / rD)^2]^beta`.
         * @param[in] size           Size specification.
         * @param[in] rType          Kind of size being specified (one of FWHM, HALF_LIGHT_RADIUS,
         *                           SCALE_RADIUS).
         * @param[in] trunc          Outer truncation radius in same physical units as size,
         *                           trunc = 0. for no truncation.
         * @param[in] flux           Flux.
         * @param[in] gsparams       GSParams object storing constants that control the accuracy of
         *                           image operations and rendering, if different from the default.
         */
        SBMoffat(double beta, double size, RadiusType rType, double trunc, double flux,
                 const GSParamsPtr& gsparams);


        /// @brief Copy constructor.
        SBMoffat(const SBMoffat& rhs);

        /// @brief Destructor.
        ~SBMoffat();

        /// @brief Returns beta of the Moffat profile `[1 + (r / rD)^2]^beta`.
        double getBeta() const;

        /// @brief Returns the FWHM of the Moffat profile.
        double getFWHM() const;

        /// @brief Returns the scale radius rD of the Moffat profile `[1 + (r / rD)^2]^beta`.
        double getScaleRadius() const;

        /// @brief Returns the half light radius of the Moffat profile.
        double getHalfLightRadius() const;

    protected:

        class SBMoffatImpl;

    private:
        // op= is undefined
        void operator=(const SBMoffat& rhs);
    };

}

#endif // SBMOFFAT_H

