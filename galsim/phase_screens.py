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

from builtins import range, zip
import numpy as np

from .random import BaseDeviate, GaussianDeviate
from .image import Image
from .angle import radians
from .table import LookupTable2D
from . import utilities
from . import fft
from . import zernike
from .errors import GalSimWarning


class AtmosphericScreen(object):
    """ An atmospheric phase screen that can drift in the wind and evolves ("boils") over time.  The
    initial phases and fractional phase updates are drawn from a von Karman power spectrum, which is
    defined by a Fried parameter that effectively sets the amplitude of the turbulence, and an outer
    scale beyond which the turbulence power flattens.

    AtmosphericScreen delays the actual instantiation of the phase screen array in memory until it
    is used for either drawing a PSF or querying the wavefront or wavefront gradient.  This is to
    facilitate automatic truncation of the screen power spectrum depending on the use case.  For
    example, when drawing a PhaseScreenPSF using Fourier methods, the entire power spectrum should
    generally be used.  On the other hand, when drawing using photon-shooting and the geometric
    approximation, it's better to truncate the high-k modes of the power spectrum here so
    that they can be handled instead by a SecondKick object (which also happens automatically; see
    the PhaseScreenPSF docstring).  (See Peterson et al. 2015 for more details about the second
    kick).  Querying the wavefront or wavefront gradient will instantiate the screen using the full
    power spectrum.

    This class will normally attempt to sanity check that the screen has been appropriately
    instantiated depending on the use case, i.e., depending on whether it's being used to draw with
    Fourier optics or geometric optics.  If you want to turn this warning off, however, you can
    use the `suppress_warning` keyword argument.

    If you wish to override the automatic truncation determination, then you can directly
    instantiate the phase screen array using the AtmosphericScreen.instantiate() method.

    Note that once a screen has been instantiated with a particular set of truncation parameters, it
    cannot be re-instantiated with another set of parameters.

    @param screen_size   Physical extent of square phase screen in meters.  This should be large
                         enough to accommodate the desired field-of-view of the telescope as well as
                         the meta-pupil defined by the wind speed and exposure time.  Note that
                         the screen will have periodic boundary conditions, so while the code will
                         still run with a small screen, this may introduce artifacts into PSFs or
                         PSF correlation functions.  Also note that screen_size may be tweaked by
                         the initializer to ensure `screen_size` is a multiple of `screen_scale`.
    @param screen_scale  Physical pixel scale of phase screen in meters.  An order unity multiple of
                         the Fried parameter is usually sufficiently small, but users should test
                         the effects of varying this parameter to ensure robust results.
                         [default: r0_500]
    @param altitude      Altitude of phase screen in km.  This is with respect to the telescope, not
                         sea-level.  [default: 0.0]
    @param r0_500        Fried parameter setting the amplitude of turbulence; contributes to "size"
                         of the resulting atmospheric PSF.  Specified at wavelength 500 nm, in units
                         of meters.  [default: 0.2]
    @param L0            Outer scale in meters.  The turbulence power spectrum will smoothly
                         approach a constant at scales larger than L0.  Set to `None` or `np.inf`
                         for a power spectrum without an outer scale.  [default: 25.0]
    @param vx            x-component wind velocity in meters/second.  [default: 0.]
    @param vy            y-component wind velocity in meters/second.  [default: 0.]
    @param alpha         Square root of fraction of phase that is "remembered" between time_steps
                         (i.e., alpha**2 is the fraction remembered). The fraction sqrt(1-alpha**2)
                         is then the amount of turbulence freshly generated in each step.  Setting
                         alpha=1.0 results in a frozen-flow atmosphere.  Note that computing PSFs
                         from frozen-flow atmospheres may be significantly faster than computing
                         PSFs with non-frozen-flow atmospheres.  If `alpha` != 1.0, then it is
                         required that a `time_step` is also specified.  [default: 1.0]
    @param time_step     Time interval between phase boiling updates.  Note that this is distinct
                         from the time interval used to integrate the PSF over time, which is set
                         by the `time_step` keyword argument to `PhaseScreenPSF` or
                         `PhaseScreenList.makePSF`.  If `time_step` is not None, then it is required
                         that `alpha` is set to something other than 1.0.  [default: None]
    @param rng           Random number generator as a galsim.BaseDeviate().  If None, then use the
                         clock time or system entropy to seed a new generator.  [default: None]
    @param suppress_warning   Turn off instantiation sanity checking.  (See above)  [default: False]

    Relevant SPIE paper:
    "Remembrance of phases past: An autoregressive method for generating realistic atmospheres in
    simulations"
    Srikar Srinath, Univ. of California, Santa Cruz;
    Lisa A. Poyneer, Lawrence Livermore National Lab.;
    Alexander R. Rudy, UCSC; S. Mark Ammons, LLNL
    Published in Proceedings Volume 9148: Adaptive Optics Systems IV
    September 2014
    """
    def __init__(self, screen_size, screen_scale=None, altitude=0.0, r0_500=0.2, L0=25.0,
                 vx=0.0, vy=0.0, alpha=1.0, time_step=None, rng=None, suppress_warning=False):

        if (alpha != 1.0 and time_step is None):
            raise ValueError("No time_step provided when alpha != 1.0")
        if (alpha == 1.0 and time_step is not None):
            raise ValueError("Setting AtmosphericScreen time_step prohibited when alpha == 1.0.  "
                             "Did you mean to set time_step in makePSF or PhaseScreenPSF?")
        if screen_scale is None:
            # We copy Jee+Tyson(2011) and (arbitrarily) set the screen scale equal to r0 by default.
            screen_scale = r0_500
        self.npix = Image.good_fft_size(int(np.ceil(screen_size/screen_scale)))
        self.screen_scale = screen_scale
        self.screen_size = screen_scale * self.npix
        self.altitude = altitude
        self.time_step = time_step
        self.r0_500 = r0_500
        if L0 == np.inf:  # Allow np.inf as synonym for None.
            L0 = None
        self.L0 = L0
        self.vx = vx
        self.vy = vy
        self.alpha = alpha
        self._time = 0.0

        if rng is None:
            rng = BaseDeviate()
        self._suppress_warning = suppress_warning

        self._orig_rng = rng.duplicate()
        self.dynamic = True
        self.reversible = self.alpha == 1.0

        # These will be None until screens are instantiated.
        self.kmin = None
        self.kmax = None

    def __str__(self):
        return "galsim.AtmosphericScreen(altitude=%s)" % self.altitude

    def __repr__(self):
        return ("galsim.AtmosphericScreen(%r, %r, altitude=%r, r0_500=%r, L0=%r, " +
                "vx=%r, vy=%r, alpha=%r, time_step=%r, rng=%r)") % (
                        self.screen_size, self.screen_scale, self.altitude, self.r0_500, self.L0,
                        self.vx, self.vy, self.alpha, self.time_step, self._orig_rng)

    # While AtmosphericScreen does have mutable internal state, it's still possible to treat the
    # object as hashable under the python data model.  The requirements for hashability are that
    # the hash value never changes during the lifetime of the object, __eq__ is defined, and a == b
    # implies hash(a) == hash(b).  We also require that if a == b, then f(a) == f(b) for any public
    # function on an AtmosphericScreen, such as producing a PSF.  Generally, it's a good idea to
    # try for hash(a) == hash(b) to imply that it's very likely that a == b, too.  This is mostly
    # True for AtmosphericScreen (and derived objects, like PSFs), but note that while we don't
    # use the object's mutable internal state for the hash value, we do use it for the __eq__ test.
    # In particular, the hash value doesn't change after the screen is instantiated from its value
    # before instantiation.  Equality, on the other hand, does change.  An instantiated screen is
    # not equal to an otherwise identical uninstantiated screen.

    def __eq__(self, other):
        return (isinstance(other, AtmosphericScreen) and
                self.screen_size == other.screen_size and
                self.screen_scale == other.screen_scale and
                self.altitude == other.altitude and
                self.r0_500 == other.r0_500 and
                self.L0 == other.L0 and
                self.vx == other.vx and
                self.vy == other.vy and
                self.alpha == other.alpha and
                self.time_step == other.time_step and
                self._orig_rng == other._orig_rng and
                self.kmin == other.kmin and
                self.kmax == other.kmax)

    def __hash__(self):
        if not hasattr(self, '_hash'):
            self._hash = hash((
                    "galsim.AtmosphericScreen", self.screen_size, self.screen_scale, self.altitude,
                    self.r0_500, self.L0, self.vx, self.vy, self.alpha, self.time_step,
                    repr(self._orig_rng.serialize())))
        return self._hash

    def __ne__(self, other): return not self == other

    def instantiate(self, kmin=0., kmax=np.inf, check=None):
        """
        @param kmin   Minimum k-mode to include when generating phase screens.  Generally this will
                      only be used when testing the geometric approximation for atmospheric PSFs.
                      [default: 0]
        @param kmax   Maximum k-mode to include when generating phase screens.  This may be used in
                      conjunction with SecondKick to complete the geometric approximation for
                      atmospheric PSFs.  [default: np.inf]
        @param check  Sanity check indicator.  If equal to 'FFT', then check that phase screen
                      Fourier modes are not being truncated, which is appropriate for full Fourier
                      optics.  If equal to 'phot', then check that phase screen Fourier modes *are*
                      being truncated, which is appropriate for the geometric optics approximation.
                      If `None`, then don't perform a check.  Also, don't perform a check if
                      self.suppress_warning is True.
        """
        if self.kmax is None:
            self.kmin = kmin
            self.kmax = kmax
            self._init_psi()
            self._reset()
            # Free some RAM for frozen-flow screens.
            if self.reversible:
                del self._psi, self._screen
        if check is not None and not self._suppress_warning:
            if check == 'FFT':
                if self.kmax != np.inf:
                    import warnings
                    warnings.warn(
                        "Instantiating AtmosphericScreen with kmax != inf "
                        "may yield surprising results when drawing using Fourier optics.",
                        GalSimWarning)
            if check == 'phot':
                if self.kmax == np.inf:
                    import warnings
                    warnings.warn(
                        "Instantiating AtmosphericScreen with kmax == inf "
                        "may yield surprising results when drawing using geometric optics.",
                        GalSimWarning)


    # Note the magic number 0.00058 is actually ... wait for it ...
    # (5 * (24/5 * gamma(6/5))**(5/6) * gamma(11/6)) / (6 * pi**(8/3) * gamma(1/6)) / (2 pi)**2
    # It's nearly impossible to figure this out from a single source, but it can be derived from a
    # combination of Roddier (1981), Sasiela (1994), and Noll (1976).  (These atmosphere people
    # sure like to work alone... )
    _kolmogorov_constant = np.sqrt(0.00058)

    def _init_psi(self):
        """Assemble 2D von Karman sqrt power spectrum.
        """
        fx = np.fft.fftfreq(self.npix, self.screen_scale)
        fx, fy = np.meshgrid(fx, fx)
        # Faster to avoid as many temporary arrays as possible.  This is just ksq = fx**2 + fy**2.
        ksq = fx
        ksq[:,:] *= fx
        ksq[:,:] += fy*fy

        # We'll use ksq as our array for psi too.  So save this mask for later.
        m = (ksq < self.kmin**2) | (ksq > self.kmax**2)

        old_settings = np.seterr(all='ignore')
        self._psi = ksq
        if self.L0 is not None:
            L0_inv = 1./self.L0
            self._psi[:,:] += L0_inv*L0_inv
        self._psi[:,:] **= -11./12.
        # Note the multiplication by 500 here so we can divide by arbitrary lam later.
        self._psi[:,:] *= (self._kolmogorov_constant * self.r0_500**(-5.0/6.0) * self.npix *
                           500. / self.screen_size)
        self._psi[0, 0] = 0.0
        self._psi[m] = 0.0
        np.seterr(**old_settings)

    def _random_screen(self):
        """Generate a random phase screen with power spectrum given by self._psi**2"""
        gd = GaussianDeviate(self.rng)
        noise = utilities.rand_arr(self._psi.shape, gd)
        return fft.ifft2(fft.fft2(noise)*self._psi).real

    def _seek(self, t):
        """Set layer's internal clock to time t."""
        if t == self._time:
            return
        if not self.reversible:
            # Can't reverse, so reset and move forward.
            if t < self._time:
                if t < 0.0:
                    raise ValueError("Can't rewind irreversible screen to t < 0.0")
                self._reset()
            # Find number of boiling updates we need to perform.
            previous_update_number = int(self._time // self.time_step)
            final_update_number = int(t // self.time_step)
            n_updates = final_update_number - previous_update_number
            if n_updates > 0:
                for _ in range(n_updates):
                    self._screen *= self.alpha
                    self._screen += np.sqrt(1.-self.alpha**2) * self._random_screen()
                self._tab2d = LookupTable2D(self._xs, self._ys, self._screen, edge_mode='wrap')
        self._time = float(t)

    def _reset(self):
        """Reset phase screen back to time=0."""
        self.rng = self._orig_rng.duplicate()
        self._time = 0.0

        # Only need to reset/create tab2d if not frozen or doesn't already exist
        if not self.reversible or not hasattr(self, '_tab2d'):
            self._screen = self._random_screen()
            self._xs = np.linspace(-0.5*self.screen_size, 0.5*self.screen_size, self.npix,
                                   endpoint=False)
            self._ys = self._xs
            self._tab2d = LookupTable2D(self._xs, self._ys, self._screen, edge_mode='wrap')

    # Note -- use **kwargs here so that AtmosphericScreen.stepk and OpticalScreen.stepk
    # can use the same signature, even though they depend on different parameters.
    def _getStepK(self, **kwargs):
        """Return an appropriate stepk for this atmospheric layer.

        @param lam         Wavelength in nanometers.
        @param scale_unit  Sky coordinate units of output profile. [default: galsim.arcsec]
        @param gsparams    An optional GSParams argument.  See the docstring for GSParams for
                           details. [default: None]
        @returns  Good pupil scale size in meters.
        """
        from .kolmogorov import Kolmogorov
        lam = kwargs['lam']
        gsparams = kwargs.pop('gsparams', None)
        obj = Kolmogorov(lam=lam, r0_500=self.r0_500, gsparams=gsparams)
        return obj.stepk

    def wavefront(self, u, v, t=None, theta=(0.0*radians, 0.0*radians)):
        """ Compute wavefront due to atmospheric phase screen.

        Wavefront here indicates the distance by which the physical wavefront lags or leads the
        ideal plane wave.

        @param u        Horizontal pupil coordinate (in meters) at which to evaluate wavefront.  Can
                        be a scalar or an iterable.  The shapes of u and v must match.
        @param v        Vertical pupil coordinate (in meters) at which to evaluate wavefront.  Can
                        be a scalar or an iterable.  The shapes of u and v must match.
        @param t        Times (in seconds) at which to evaluate wavefront.  Can be None, a scalar or
                        an iterable.  If None, then the internal time of the phase screens will be
                        used for all u, v.  If scalar, then the size will be broadcast up to match
                        that of u and v.  If iterable, then the shape must match the shapes of u and
                        v.  [default: None]
        @param theta    Field angle at which to evaluate wavefront, as a 2-tuple of `galsim.Angle`s.
                        [default: (0.0*galsim.arcmin, 0.0*galsim.arcmin)]  Only a single theta is
                        permitted.
        @returns        Array of wavefront lag or lead in nanometers.
        """
        u = np.array(u, dtype=float)
        v = np.array(v, dtype=float)
        if u.shape != v.shape:
            raise ValueError("u.shape not equal to v.shape")

        if t is None:
            t = self._time

        from numbers import Real
        if isinstance(t, Real):
            tmp = np.empty_like(u)
            tmp.fill(t)
            t = tmp
        else:
            t = np.array(t, dtype=float)
            if t.shape != u.shape:
                raise ValueError("t.shape must match u.shape if t is not a scalar")

        self.instantiate()  # noop if already instantiated

        if self.reversible:
            return self._wavefront(u, v, t, theta)
        else:
            out = np.empty_like(u, dtype=float)
            tmin = np.min(t)
            tmax = np.max(t)
            tt = (tmin // self.time_step) * self.time_step
            while tt <= tmax:
                self._seek(tt)
                here = ((tt <= t) & (t < tt+self.time_step))
                out[here] = self._wavefront(u[here], v[here], t[here], theta)
                tt += self.time_step
            return out

    def _wavefront(self, u, v, t, theta):
        # Same as wavefront(), but no argument checking, no boiling updates, no
        # screen instantiation checking
        if t is None:
            t = self._time
        u = u - t*self.vx + 1000*self.altitude*theta[0].tan()
        v = v - t*self.vy + 1000*self.altitude*theta[1].tan()
        return self._tab2d(u, v)

    def wavefront_gradient(self, u, v, t=None, theta=(0.0*radians, 0.0*radians)):
        """ Compute gradient of wavefront due to atmospheric phase screen.

        @param u        Horizontal pupil coordinate (in meters) at which to evaluate wavefront.  Can
                        be a scalar or an iterable.  The shapes of u and v must match.
        @param v        Vertical pupil coordinate (in meters) at which to evaluate wavefront.  Can
                        be a scalar or an iterable.  The shapes of u and v must match.
        @param t        Times (in seconds) at which to evaluate wavefront gradient.  Can be None, a
                        scalar or an iterable.  If None, then the internal time of the phase screens
                        will be used for all u, v.  If scalar, then the size will be broadcast up to
                        match that of u and v.  If iterable, then the shape must match the shapes of
                        u and v.  [default: None]
        @param theta    Field angle at which to evaluate wavefront, as a 2-tuple of `galsim.Angle`s.
                        [default: (0.0*galsim.arcmin, 0.0*galsim.arcmin)]  Only a single theta is
                        permitted.
        @returns        Arrays dWdu and dWdv of wavefront lag or lead gradient in nm/m.
        """
        u = np.array(u, dtype=float)
        v = np.array(v, dtype=float)
        if u.shape != v.shape:
            raise ValueError("u.shape not equal to v.shape")

        from numbers import Real
        if isinstance(t, Real):
            tmp = np.empty_like(u)
            tmp.fill(t)
            t = tmp
        else:
            t = np.array(t, dtype=float)
            if t.shape != u.shape:
                raise ValueError("t.shape must match u.shape if t is not a scalar")

        self.instantiate()  # noop if already instantiated

        if self.reversible:
            return self._wavefront_gradient(u, v, t, theta)
        else:
            dwdu = np.empty_like(u, dtype=np.float64)
            dwdv = np.empty_like(u, dtype=np.float64)
            tmin = np.min(t)
            tmax = np.max(t)
            tt = (tmin // self.time_step) * self.time_step
            while tt <= tmax:
                self._seek(tt)
                here = ((tt <= t) & (t < tt+self.time_step))
                dwdu[here], dwdv[here] = self._wavefront_gradient(u[here], v[here], t[here], theta)
                tt += self.time_step
            return dwdu, dwdv

    def _wavefront_gradient(self, u, v, t, theta):
        # Same as wavefront(), but no argument checking and no boiling updates.
        u = u - t*self.vx + 1000*self.altitude*theta[0].tan()
        v = v - t*self.vy + 1000*self.altitude*theta[1].tan()
        return self._tab2d.gradient(u, v)


def Atmosphere(screen_size, rng=None, _bar=None, **kwargs):
    """Create an atmosphere as a list of turbulent phase screens at different altitudes.  The
    atmosphere model can then be used to simulate atmospheric PSFs.

    Simulating an atmospheric PSF is typically accomplished by first representing the 3-dimensional
    turbulence in the atmosphere as a series of discrete 2-dimensional phase screens.  These screens
    may blow around in the wind, and may or may not also evolve in time.  This function allows one
    to quickly assemble a list of atmospheric phase screens into a galsim.PhaseScreenList object,
    which can then be used to evaluate PSFs through various columns of atmosphere at different field
    angles.

    The atmospheric screens currently available represent turbulence following a von Karman power
    spectrum.  Specifically, the phase power spectrum in each screen can be written

    psi(nu) = 0.023 r0^(-5/3) (nu^2 + 1/L0^2)^(11/6)

    where psi(nu) is the power spectral density at spatial frequency nu, r0 is the Fried parameter
    (which has dimensions of length) and sets the amplitude of the turbulence, and L0 is the outer
    scale (also dimensions of length) beyond which the power asymptotically flattens.  Typical
    values for r0 are ~0.1 to 0.2 meters, which corresponds roughly to PSF FWHMs of ~0.5 to 1.0
    arcsec for optical wavelengths.  Note that r0 is a function of wavelength, scaling like
    r0 ~ wavelength^(6/5).  To reduce confusion, the input parameter here is named r0_500 and refers
    explicitly to the Fried parameter at a wavelength of 500 nm.  The outer scale is typically in
    the 10s of meters and does not vary with wavelength.

    To create multiple layers, simply specify keyword arguments as length-N lists instead of scalars
    (works for all arguments except `rng`).  If, for any of these keyword arguments, you want to use
    the same value for each layer, then you can just specify the argument as a scalar and the
    function will automatically broadcast it into a list with length equal to the longest found
    keyword argument list.  Note that it is an error to specify keywords with lists of different
    lengths (unless only one of them has length > 1).

    The one exception to the above is the keyword `r0_500`.  The effective Fried parameter for a set
    of atmospheric layers is r0_500_effective = (sum(r**(-5./3) for r in r0_500s))**(-3./5).
    Providing `r0_500` as a scalar or single-element list will result in broadcasting such that the
    effective Fried parameter for the whole set of layers equals the input argument.  You can weight
    the contribution of each layer with the `r0_weights` keyword.

    As an example, the following code approximately creates the atmosphere used by Jee+Tyson(2011)
    for their study of atmospheric PSFs for LSST.  Note this code takes about ~2 minutes to run on
    a fast laptop, and will consume about (8192**2 pixels) * (8 bytes) * (6 screens) ~ 3 GB of
    RAM in its final state, and more at intermediate states.

        >>> altitude = [0, 2.58, 5.16, 7.73, 12.89, 15.46]  # km
        >>> r0_500 = 0.16  # m
        >>> weights = [0.652, 0.172, 0.055, 0.025, 0.074, 0.022]
        >>> speed = np.random.uniform(0, 20, size=6)  # m/s
        >>> direction = [np.random.uniform(0, 360)*galsim.degrees for i in range(6)]
        >>> npix = 8192
        >>> screen_scale = r0_500
        >>> atm = galsim.Atmosphere(r0_500=r0_500, r0_weights=weights,
                                    screen_size=screen_scale*npix,
                                    altitude=altitude, L0=25.0, speed=speed,
                                    direction=direction, screen_scale=screen_scale)

    Once the atmosphere is constructed, a 15-sec exposure length, 5ms time step, monochromatic PSF
    at 700nm (using an 8.4 meter aperture, 0.6 fractional obscuration and otherwise default
    settings) takes about 7 minutes to draw on a fast laptop.

        >>> psf = atm.makePSF(lam=700.0, exptime=15.0, time_step=0.005, diam=8.4, obscuration=0.6)
        >>> img1 = psf.drawImage()  # ~7 min

    The same psf, if drawn using photon-shooting on the same laptop, will generate photons at a rate
    of about 1 million per second.

        >>> img2 = psf.drawImage(nx=32, ny=32, scale=0.2, method='phot', n_photons=1e6)  # ~1 sec.

    Note that the Fourier-based calculation compute time will scale linearly with exposure time,
    while the photon-shooting calculation compute time will scale linearly with the number of
    photons being shot.

    Many factors will affect the timing of results, of course, including aperture diameter, gsparams
    settings, pad_factor and oversampling options to makePSF, time_step and exposure time, frozen
    vs. non-frozen atmospheric layers, and so on.  We recommend that users try varying these
    settings to find a balance of speed and fidelity.

    @param r0_500        Fried parameter setting the amplitude of turbulence; contributes to "size"
                         of the resulting atmospheric PSF.  Specified at wavelength 500 nm, in units
                         of meters.  [default: 0.2]
    @param r0_weights    Weights for splitting up the contribution of r0_500 between different
                         layers.  Note that this keyword is only allowed if r0_500 is either a
                         scalar or a single-element list.  [default: None]
    @param screen_size   Physical extent of square phase screen in meters.  This should be large
                         enough to accommodate the desired field-of-view of the telescope as well as
                         the meta-pupil defined by the wind speed and exposure time.  Note that
                         the screen will have periodic boundary conditions, so the code will run
                         with a smaller sized screen, though this may introduce artifacts into PSFs
                         or PSF correlation functions. Note that screen_size may be tweaked by the
                         initializer to ensure screen_size is a multiple of screen_scale.
    @param screen_scale  Physical pixel scale of phase screen in meters.  A fraction of the Fried
                         parameter is usually sufficiently small, but users should test the effects
                         of this parameter to ensure robust results.
                         [default: same as each screen's r0_500]
    @param altitude      Altitude of phase screen in km.  This is with respect to the telescope, not
                         sea-level.  [default: 0.0]
    @param L0            Outer scale in meters.  The turbulence power spectrum will smoothly
                         approach a constant at scales larger than L0.  Set to `None` or `np.inf`
                         for a power spectrum without an outer scale.  [default: 25.0]
    @param speed         Wind speed in meters/second.  [default: 0.0]
    @param direction     Wind direction as galsim.Angle [default: 0.0 * galsim.degrees]
    @param alpha         Square root of fraction of phase that is "remembered" between time_steps
                         (i.e., alpha**2 is the fraction remembered). The fraction sqrt(1-alpha**2)
                         is then the amount of turbulence freshly generated in each step.  Setting
                         alpha=1.0 results in a frozen-flow atmosphere.  Note that computing PSFs
                         from frozen-flow atmospheres may be significantly faster than computing
                         PSFs with non-frozen-flow atmospheres.  [default: 1.0]
    @param time_step     Time interval between phase boiling updates.  Note that this is distinct
                         from the time interval used when integrating the PSF over time, which is
                         set by the `time_step` keyword argument to `PhaseScreenPSF` or
                         `PhaseScreenList.makePSF`.  If `time_step` is not None, then it is required
                         that `alpha` is set to something other than 1.0.  [default: None]
    @param rng           Random number generator as a galsim.BaseDeviate().  If None, then use the
                         clock time or system entropy to seed a new generator.  [default: None]
    """
    from .phase_psf import PhaseScreenList
    # Fill in screen_size here, since there isn't a default in AtmosphericScreen
    kwargs['screen_size'] = utilities.listify(screen_size)

    # Set default r0_500 here; it will get broadcasted below such that the _total_ r0_500 from _all_
    # screens is 0.2 m.
    if 'r0_500' not in kwargs:
        kwargs['r0_500'] = [0.2]
    kwargs['r0_500'] = utilities.listify(kwargs['r0_500'])

    # Turn speed, direction into vx, vy
    if 'speed' in kwargs:
        kwargs['speed'] = utilities.listify(kwargs['speed'])
        if 'direction' not in kwargs:
            kwargs['direction'] = [0*radians]*len(kwargs['speed'])
        kwargs['vx'], kwargs['vy'] = zip(*[v * np.array(d.sincos())
                                           for v, d in zip(kwargs['speed'],
                                                           kwargs['direction'])])
        del kwargs['speed']
        del kwargs['direction']

    # Determine broadcast size
    nmax = max(len(v) for v in kwargs.values() if hasattr(v, '__len__'))

    # Broadcast r0_500 here, since logical combination of indiv layers' r0s is complex:
    if len(kwargs['r0_500']) == 1:
        r0_weights = np.array(kwargs.pop('r0_weights', [1.]*nmax), dtype=float)
        r0_weights /= np.sum(r0_weights)
        r0_500 = kwargs['r0_500'][0]
        kwargs['r0_500'] = [r0_500 * w**(-3./5) for w in r0_weights]
        # kwargs['r0_500'] = [nmax**(3./5) * kwargs['r0_500'][0]] * nmax
    elif 'r0_weights' in kwargs:
        raise ValueError("Cannot use r0_weights if r0_500 is specified as a list.")

    if rng is None:
        rng = BaseDeviate()
    kwargs['rng'] = [BaseDeviate(rng.raw()) for i in range(nmax)]
    return PhaseScreenList([AtmosphericScreen(**kw) for kw in utilities.dol_to_lod(kwargs, nmax)])


class OpticalScreen(object):
    """
    Class to describe optical aberrations in terms of Zernike polynomial coefficients.

    Input aberration coefficients are assumed to be supplied in units of wavelength, and correspond
    to the Zernike polynomials in the Noll convention defined in
    Noll, J. Opt. Soc. Am. 66, 207-211(1976).  For a brief summary of the polynomials, refer to
    http://en.wikipedia.org/wiki/Zernike_polynomials#Zernike_polynomials.

    @param diam             Diameter of pupil in meters.
    @param tip              Tip aberration in units of reference wavelength.  [default: 0]
    @param tilt             Tilt aberration in units of reference wavelength.  [default: 0]
    @param defocus          Defocus in units of reference wavelength. [default: 0]
    @param astig1           Astigmatism (like e2) in units of reference wavelength.
                            [default: 0]
    @param astig2           Astigmatism (like e1) in units of reference wavelength.
                            [default: 0]
    @param coma1            Coma along y in units of reference wavelength. [default: 0]
    @param coma2            Coma along x in units of reference wavelength. [default: 0]
    @param trefoil1         Trefoil (one of the arrows along y) in units of reference wavelength.
                            [default: 0]
    @param trefoil2         Trefoil (one of the arrows along x) in units of reference wavelength.
                            [default: 0]
    @param spher            Spherical aberration in units of reference wavelength.
                            [default: 0]
    @param aberrations      Optional keyword, to pass in a list, tuple, or NumPy array of
                            aberrations in units of reference wavelength (ordered according to
                            the Noll convention), rather than passing in individual values for each
                            individual aberration.  Note that aberrations[1] is piston (and not
                            aberrations[0], which is unused.)  This list can be arbitrarily long to
                            handle Zernike polynomial aberrations of arbitrary order.
    @param annular_zernike  Boolean indicating that aberrations specify the amplitudes of annular
                            Zernike polynomials instead of circular Zernike polynomials.
                            [default: False]
    @param obscuration      Linear dimension of central obscuration as fraction of aperture linear
                            dimension. [0., 1.).  Note it is the user's responsibility to ensure
                            consistency of OpticalScreen obscuration and Aperture obscuration.
                            [default: 0.0]
    @param lam_0            Reference wavelength in nanometers at which Zernike aberrations are
                            being specified.  [default: 500]
    """
    def __init__(self, diam, tip=0.0, tilt=0.0, defocus=0.0, astig1=0.0, astig2=0.0, coma1=0.0,
                 coma2=0.0, trefoil1=0.0, trefoil2=0.0, spher=0.0, aberrations=None,
                 annular_zernike=False, obscuration=0.0, lam_0=500.0):
        self.diam = diam
        if aberrations is None:
            aberrations = np.zeros(12)
            aberrations[2] = tip
            aberrations[3] = tilt
            aberrations[4] = defocus
            aberrations[5] = astig1
            aberrations[6] = astig2
            aberrations[7] = coma1
            aberrations[8] = coma2
            aberrations[9] = trefoil1
            aberrations[10] = trefoil2
            aberrations[11] = spher
        else:
            # Make sure no individual aberrations were passed in, since they will be ignored.
            if any([tip, tilt, defocus, astig1, astig2, coma1, coma2, trefoil1, trefoil2, spher]):
                raise TypeError("Cannot pass in individual aberrations and array!")
            # Aberrations were passed in, so check for right number of entries.
            if len(aberrations) <= 2:
                raise ValueError("Aberrations keyword must have length > 2")
            # Check for non-zero value in first two places.  Probably a mistake.
            if aberrations[0] != 0.0:
                import warnings
                warnings.warn(
                    "Detected non-zero value in aberrations[0] -- this value is ignored!",
                    GalSimWarning)
            aberrations = np.array(aberrations)
        self.aberrations = aberrations

        # strip any trailing zeros.
        if self.aberrations[-1] == 0:
            self.aberrations = np.trim_zeros(self.aberrations, trim='b')
            if len(self.aberrations) == 0:  # Don't let it be zero length.
                self.aberrations = np.array([0])
        self.annular_zernike = annular_zernike
        self.obscuration = obscuration
        self.lam_0 = lam_0

        R_outer = self.diam/2
        if self.annular_zernike and self.obscuration != 0:
            self._zernike = zernike.Zernike(self.aberrations, R_outer=R_outer,
                                            R_inner=R_outer*self.obscuration)
        else:
            self._zernike = zernike.Zernike(self.aberrations, R_outer=R_outer)

        self.dynamic = False
        self.reversible = True

    def __str__(self):
        return "galsim.OpticalScreen(diam=%s, lam_0=%s)" % (self.diam, self.lam_0)

    def __repr__(self):
        s = "galsim.OpticalScreen(diam=%r, lam_0=%r" % (self.diam, self.lam_0)
        if any(self.aberrations):
            s += ", aberrations=%r"%self.aberrations
        if self.annular_zernike:
            s += ", annular_zernike=True"
            s += ", obscuration=%r"%self.obscuration
        s += ")"
        return s

    def __eq__(self, other):
        return (isinstance(other, OpticalScreen)
                and self.diam == other.diam
                and np.array_equal(self.aberrations*self.lam_0, other.aberrations*other.lam_0)
                and self.annular_zernike == other.annular_zernike)

    def __ne__(self, other): return not self == other

    # This screen is immutable, so make a hash for it.
    def __hash__(self):
        return hash(("galsim.OpticalScreen", self.diam, self.obscuration, self.annular_zernike,
                     tuple((self.aberrations*self.lam_0).ravel())))

    # Note -- use **kwargs here so that AtmosphericScreen.stepk and OpticalScreen.stepk
    # can use the same signature, even though they depend on different parameters.
    def _getStepK(self, **kwargs):
        """Return an appropriate stepk for this phase screen.

        @param lam         Wavelength in nanometers.
        @param diam        Aperture diameter in meters.
        @param obscuration Fractional linear aperture obscuration. [default: 0.0]
        @param gsparams    An optional GSParams argument.  See the docstring for GSParams for
                           details. [default: None]
        @returns stepk in inverse arcsec.
        """
        from .airy import Airy
        lam = kwargs['lam']
        diam = kwargs['diam']
        obscuration = kwargs.get('obscuration', 0.0)
        gsparams = kwargs.get('gsparams', None)
        # Use an Airy for get appropriate stepk.
        obj = Airy(lam=lam, diam=diam, obscuration=obscuration, gsparams=gsparams)
        return obj.stepk

    def wavefront(self, u, v, t=None, theta=None):
        """ Compute wavefront due to optical phase screen.

        Wavefront here indicates the distance by which the physical wavefront lags or leads the
        ideal plane wave.

        @param u        Horizontal pupil coordinate (in meters) at which to evaluate wavefront.  Can
                        be a scalar or an iterable.  The shapes of u and v must match.
        @param v        Vertical pupil coordinate (in meters) at which to evaluate wavefront.  Can
                        be a scalar or an iterable.  The shapes of u and v must match.
        @param t        Ignored for OpticalScreen.
        @param theta    Ignored for OpticalScreen.
        @returns        Array of wavefront lag or lead in nanometers.
        """
        u = np.array(u, dtype=float)
        v = np.array(v, dtype=float)
        if u.shape != v.shape:
            raise ValueError("u.shape not equal to v.shape")
        return self._wavefront(u, v, t, theta)

    def _wavefront(self, u, v, t, theta):
        # Same as wavefront(), but no argument checking.
        # Note, this phase screen is actually independent of time and theta.
        return self._zernike.evalCartesian(u, v) * self.lam_0

    def wavefront_gradient(self, u, v, t=None, theta=None):
        """ Compute gradient of wavefront due to optical phase screen.

        @param u        Horizontal pupil coordinate (in meters) at which to evaluate wavefront.  Can
                        be a scalar or an iterable.  The shapes of u and v must match.
        @param v        Vertical pupil coordinate (in meters) at which to evaluate wavefront.  Can
                        be a scalar or an iterable.  The shapes of u and v must match.
        @param t        Ignored for OpticalScreen.
        @param theta    Ignored for OpticalScreen.
        @returns        Arrays dWdu and dWdv of wavefront lag or lead gradient in nm/m.
        """
        u = np.array(u, dtype=float)
        v = np.array(v, dtype=float)
        if u.shape != v.shape:
            raise ValueError("u.shape not equal to v.shape")
        return self._wavefront_gradient(u, v, t, theta)


    def _wavefront_gradient(self, u, v, t, theta):
        # Same as wavefront(), but no argument checking.
        # Note, this phase screen is actually independent of time and theta.
        gradx, grady = self._zernike.evalCartesianGrad(u, v)
        return gradx * self.lam_0, grady * self.lam_0
