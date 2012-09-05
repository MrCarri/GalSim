import galsim

class Shift:
    """@brief A simple class representing (dx,dy)
    """
    def __init__(self, dx, dy):
        self.dx = dx
        self.dy = dy
    def __str__(self):
        return 'Shift(dx='+str(self.dx)+',dy='+str(self.dy)+')'


def ParseValue(config, param_name, base, value_type):
    """@brief Read or generate a parameter value from config.

    @return value, safe
    """
    param = config[param_name]
    #print 'ParseValue for param_name = ',param_name,', value_type = ',str(value_type)
    #print 'param = ',param

    # First see if we can assign by param by a direct constant value
    if isinstance(param, value_type):
        #print 'param == value_type: ',param,True
        return param, True
    elif not isinstance(param, dict):
        if value_type is galsim.Angle:
            # Angle is a special case.  Angles are specified with a final string to 
            # declare what unit to use.
            val = _GetAngleValue(param, param_name)
        elif value_type is bool:
            # For bool, we allow a few special string conversions
            val = _GetBoolValue(param, param_name)
        else:
            # Make sure strings are converted to float (or other type) if necessary.
            # In particular things like 1.e6 aren't converted to float automatically
            # by the yaml reader. (Although I think this is a bug.)
            try: 
                val = value_type(param)
            except:
                raise AttributeError(
                    "Could not convert %s param = %s to type %s."%(param_name,param,value_type))
        # Save the converted type for next time.
        config[param_name] = val
        #print 'param => value_type: ',val,True
        return val, True
    elif 'type' not in param:
        raise AttributeError(
            "%s.type attribute required in config for non-constant parameter %s."
                    %(param_name,param_name))
    else:
        # Otherwise, we need to generate the value according to its type
        from galsim import Angle
        from galsim import Shear
        valid_types = {
            float : [ 'InputCatalog', 'Random', 'RandomGaussian', 'Sequence', 'List' ],
            int : [ 'InputCatalog', 'Random', 'Sequence', 'List' ],
            bool : [ 'InputCatalog', 'Random', 'Sequence', 'List' ],
            str : [ 'InputCatalog', 'List' ],
            Angle : [ 'Random', 'RandomAngle', 'List' ],
            Shear : [ 'E1E2', 'EBeta', 'G1G2', 'GBeta', 'Eta1Eta2', 'EtaBeta', 'QBeta',
                      'Ring', 'List' ],
            Shift : [ 'DXDY', 'RandomCircle', 'List' ] 
        }

        type = param['type']
        #print 'type = ',type

        # First check if the value_type is valid.
        if value_type not in valid_types.keys():
            raise AttributeError(
                "Unrecognized value_type = %s in ParseValue"%value_type)
            
        if type not in valid_types[value_type]:
            raise AttributeError(
                "Invalid value for %s.type=%s with value_type = %s."%(param_name,type,value_type))

        generate_func = eval('_GenerateFrom' + type)
        #print 'generate_func = ',generate_func
        val, safe = generate_func(param, param_name, base, value_type)
        #print 'returned val, safe = ',val,safe

        # Make sure we really got the right type back.  (Just in case...)
        try : 
            if not isinstance(val,value_type):
                val = value_type(val)
        except :
            raise AttributeError(
                "Could not convert %s param = %s to type %s."%(param_name,val,value_type))
        param['current_val'] = val
        #print param_name,' = ',val
        return val, safe


def _GetAngleValue(param, param_name):
    """ @brief Convert a string consisting of a value and an angle unit into an Angle.
    """
    try :
        (value, unit) = param.rsplit(None,1)
        value = float(value)
        unit = unit.lower()
        if unit.startswith('rad') :
            return galsim.Angle(value, galsim.radians)
        elif unit.startswith('deg') :
            return galsim.Angle(value, galsim.degrees)
        elif unit.startswith('hour') :
            return galsim.Angle(value, galsim.hours)
        elif unit.startswith('hr') :
            return galsim.Angle(value, galsim.hours)
        elif unit.startswith('arcmin') :
            return galsim.Angle(value, galsim.arcmin)
        elif unit.startswith('arcsec') :
            return galsim.Angle(value, galsim.arcsec)
        else :
            raise AttributeError("Unknown Angle unit: %s for %s param"%(unit,param_name))
    except :
        raise AttributeError("Unable to parse %s param = %s as an Angle."%(param_name,param))


def _GetBoolValue(param, param_name):
    """ @brief Convert a string to a bool
    """
    #print 'GetBoolValue: param = ',param
    if isinstance(param,str):
        #print 'param.strip.upper = ',param.strip().upper()
        if param.strip().upper() in [ 'TRUE', 'YES', '1' ]:
            return True
        elif param.strip().upper() in [ 'FALSE', 'NO', '0' ]:
            return False
        else:
            raise AttributeError("Unable to parse %s param = %s as a bool."%(param_name,param))
    else:
        try:
            val = bool(param)
            return val
        except:
            raise AttributeError("Unable to parse %s param = %s as a bool."%(param_name,param))


def CheckAllParams(param, param_name, req={}, opt={}, single=[], ignore=[]):
    """@brief Check that the parameters for a particular item are all valid
    
    @return a dict, get, with get[key] = value_type for all keys to get
    """
    get = {}
    valid_keys = req.keys() + opt.keys()
    # Check required items:
    for (key, value_type) in req.items():
        if key in param:
            get[key] = value_type
        else:
            raise AttributeError(
                "Attribute %s is required for %s.type = %s"%(key,param_name,param['type']))

    # Check optional items:
    for (key, value_type) in opt.items():
        if key in param:
            get[key] = value_type

    # Check items for which exacly 1 should be defined:
    for s in single: 
        if not s: # If no items in list, don't require one of them to be present.
            break
        valid_keys += s.keys()
        count = 0
        for (key, value_type) in s.items():
            if key in param:
                count += 1
                if count > 1:
                    raise AttributeError(
                        "Only one of the attributes %s is allowed for %s.type = %s"%(
                            s.keys(),param_name,param['type']))
                get[key] = value_type
        if count == 0:
            raise AttributeError(
                "One of the attributes %s is required for %s.type = %s"%(
                    s.keys(),param_name,param['type']))

    # Check that there aren't any extra keys in param:
    valid_keys += ignore
    valid_keys += [ 'type', 'current_val' ]  # These might be there, and it's ok.
    valid_keys += [ '#' ] # When we read in json files, there represent comments
    for key in param.keys():
        if key not in valid_keys:
            raise AttributeError(
                "Unexpected attribute %s found for parameter %s"%(key,param_name))

    return get

def GetAllParams(param, param_name, base, req={}, opt={}, single=[], ignore=[]):
    """@brief Check and get all the parameters for a particular item

    @return kwargs, safe
    """
    get = CheckAllParams(param,param_name,req,opt,single,ignore)
    kwargs = {}
    safe = True
    for (key, value_type) in sorted(get.items()):
        val, safe1 = ParseValue(param, key, base, value_type)
        safe = safe1 and safe
        kwargs[key] = val
    # Just in case there are unicode strings.   python 2.6 doesn't like them in kwargs.
    kwargs = dict([(k.encode('utf-8'), v) for k,v in kwargs.iteritems()])
    return kwargs, safe

def GetCurrentValue(config, param_name):
    """@brief Return the current value of a parameter (either stored or a simple value)
    """
    param = config[param_name]
    if isinstance(param, dict):
        return param['current_val']
    else: 
        return param


#
# Now all the GenerateFrom functions:
#

def _GenerateFromG1G2(param, param_name, base, value_type):
    """@brief Return a Shear constructed from given (g1, g2)
    """
    req = { 'g1' : float, 'g2' : float }
    kwargs, safe = GetAllParams(param, param_name, base, req=req)
    #print 'Generate from G1G2: kwargs = ',kwargs
    return galsim.Shear(**kwargs), safe

def _GenerateFromE1E2(param, param_name, base, value_type):
    """@brief Return a Shear constructed from given (e1, e2)
    """
    req = { 'e1' : float, 'e2' : float }
    kwargs, safe = GetAllParams(param, param_name, base, req=req)
    return galsim.Shear(**kwargs), safe

def _GenerateFromEta1Eta2(param, param_name, base, value_type):
    """@brief Return a Shear constructed from given (eta1, eta2)
    """
    req = { 'eta1' : float, 'eta2' : float }
    kwargs, safe = GetAllParams(param, param_name, base, req=req)
    return galsim.Shear(**kwargs), safe

def _GenerateFromGBeta(param, param_name, base, value_type):
    """@brief Return a Shear constructed from given (g, beta)
    """
    req = { 'g' : float, 'beta' : galsim.Angle }
    kwargs, safe = GetAllParams(param, param_name, base, req=req)
    return galsim.Shear(**kwargs), safe

def _GenerateFromEBeta(param, param_name, base, value_type):
    """@brief Return a Shear constructed from given (e, beta)
    """
    req = { 'e' : float, 'beta' : galsim.Angle }
    kwargs, safe = GetAllParams(param, param_name, base, req=req)
    return galsim.Shear(**kwargs), safe

def _GenerateFromEtaBeta(param, param_name, base, value_type):
    """@brief Return a Shear constructed from given (eta, beta)
    """
    req = { 'eta' : float, 'beta' : galsim.Angle }
    kwargs, safe = GetAllParams(param, param_name, base, req=req)
    return galsim.Shear(**kwargs), safe

def _GenerateFromQBeta(param, param_name, base, value_type):
    """@brief Return a Shear constructed from given (q, beta)
    """
    req = { 'q' : float, 'beta' : galsim.Angle }
    kwargs, safe = GetAllParams(param, param_name, base, req=req)
    return galsim.Shear(**kwargs), safe

def _GenerateFromDXDY(param, param_name, base, value_type):
    """@brief Return a Shift constructed from given (dx,dy)
    """
    req = { 'dx' : float, 'dy' : float }
    kwargs, safe = GetAllParams(param, param_name, base, req=req)
    return galsim.config.Shift(**kwargs), safe

def _GenerateFromRing(param, param_name, base, value_type):
    """@brief Return the next shear for a ring test.
    """
    req = { 'num' : int, 'first' : galsim.Shear }
    ignore = [ 'i', 'current' ]
    # Only Check, not Get.  We don't want to generate first if it's not time yet.
    CheckAllParams(param, param_name, req=req, ignore=ignore)

    num, safe = ParseValue(param, 'num', base, int)
    #print 'In Ring parameter'
    # We store the current index in the ring and the last value in the dictionary,
    # so they will be available next time we get here.
    i = param.get('i',num)
    #print 'i = ',i
    if i == num:
        #print 'at i = num'
        current, safe = ParseValue(param, 'first', base, galsim.Shear)
        i = 1
    elif num == 2:  # Special easy case for only 2 in ring.
        #print 'i = ',i,' Simple case of n=2'
        current = -param['current']
        #print 'ring beta = ',current.beta
        #print 'ring ellip = ',current.e
        i = i + 1
    else:
        import math
        #print 'i = ',i
        s = param['current']
        current = galsim.Shear(g=s.g, beta=s.beta + math.pi/num * galsim.radians)
        #print 'ring beta = ',current.beta
        #print 'ring ellip = ',current.e
        i = i + 1
    param['i'] = i
    param['current'] = current
    #print 'return shear = ',current
    return current, False

def _GenerateFromInputCatalog(param, param_name, base, value_type):
    """@brief Return a value read from an input catalog
    """
    if 'catalog' not in base:
        raise ValueError("No input catalog available for %s.type = InputCatalog"%param_name)
    input_cat = base['catalog']

    # Setup the indexing sequence if it hasn't been specified.
    # The normal thing with an InputCatalog is to just use each object in order,
    # so we don't require the user to specify that by hand.  We can do it for them.
    SetDefaultIndex(param, input_cat.nobjects)

    req = { 'col' : int , 'index' : int }
    kwargs, safe = GetAllParams(param, param_name, base, req=req)

    col = kwargs['col']
    if col >= input_cat.ncols:
        raise IndexError("%s.col attribute (=%d) out of bounds"%(param_name,col))

    index = kwargs['index']
    if index >= input_cat.nobjects:
        raise IndexError(
            "%s index has gone past the number of entries in the catalog"%param_name)

    str = input_cat.data[index, col]
    # We want to parse this string with ParseValue, but we need a dict to do that:
    temp_dict = { param_name : str }
    val = ParseValue(temp_dict,param_name,base,value_type)[0]

    #print 'InputCatalog: ',str,val
    return val, False

def _GenerateFromRandom(param, param_name, base, value_type):
    """@brief Return a random value drawn from a uniform distribution
    """
    if 'rng' not in base:
        raise ValueError("No rng available for %s.type = Random"%param_name)
    rng = base['rng']

    # Set defaults when reasonable:
    if value_type is bool:
        param.setdefault('min',0)
        param.setdefault('max',1)
    if value_type is galsim.Angle:
        param.setdefault('min',0 * galsim.degrees)
        param.setdefault('max',360 * galsim.degrees)

    req = { 'min' : value_type , 'max' : value_type }
    kwargs, safe = GetAllParams(param, param_name, base, req=req)

    min = kwargs['min']
    max = kwargs['max']

    ud = galsim.UniformDeviate(rng)
    if value_type in [ int, bool ]:
        import math
        val = int(math.floor(ud() * (max-min+1))) + min
        # In case ud() == 1
        if val > max:
            val = max
    else:
        val = ud() * (max-min) + min
    return val, False

def _GenerateFromRandomGaussian(param, param_name, base, value_type):
    """@brief Return a random value drawn from a Gaussian distribution
    """
    if 'rng' not in base:
        raise ValueError("No rng available for %s.type = RandomGaussian"%param_name)
    rng = base['rng']

    req = { 'sigma' : float }
    opt = { 'mean' : float, 'min' : float, 'max' : float }
    kwargs, safe = GetAllParams(param, param_name, base, req=req, opt=opt)

    sigma = kwargs['sigma']

    if 'gd' in base:
        # Minor subtlety here.  GaussianDeviate requires two random numbers to 
        # generate a single Gaussian deviate.  But then it gets a second 
        # deviate for free.  So it's more efficient to store gd than to make
        # a new one each time.  So check if we did that.
        gd = base['gd']
        if base['current_gdsigma'] != sigma:
            gd.setSigma(sigma)
            base['current_gdsigma'] = sigma
    else:
        # Otherwise, just go ahead and make a new one.
        gd = galsim.GaussianDeviate(rng,sigma=sigma)
        base['gd'] = gd
        base['current_gdsigma'] = sigma

    if 'min' in kwargs or 'max' in kwargs:
        # Clip at min/max.
        # However, special cases if min == mean or max == mean
        #  -- can use fabs to double the chances of falling in the range.
        mean = kwargs.get('mean',0.)
        min = kwargs.get('min',-float('inf'))
        max = kwargs.get('max',float('inf'))

        do_abs = False
        do_neg = False
        if min == mean:
            do_abs = True
            max -= mean
            min = -max
        elif max == mean:
            do_abs = True
            do_neg = True
            min -= mean
            max = -min
        else:
            min -= mean
            max -= mean
    
        # Emulate a do-while loop
        #print 'sigma = ',sigma
        while True:
            val = gd()
            #print 'val = ',val
            if do_abs:
                import math
                val = math.fabs(val)
            if val >= min and val <= max:
                break
        if do_neg:
            val = -val
        val += mean
    else:
        val = gd()
        if 'mean' in kwargs:
            val += kwargs['mean']

    #print 'ellip = ',val
    #print 'RandomGaussian: ',val
    return val, False

def _GenerateFromRandomCircle(param, param_name, base, value_type):
    """@brief Return a Shift drawn from a circular top hat distribution.
    """
    if 'rng' not in base:
        raise ValueError("No rng available for %s.type = RandomCircle"%param_name)
    rng = base['rng']

    req = { 'radius' : float }
    kwargs, safe = GetAllParams(param, param_name, base, req=req)
    radius = kwargs['radius']

    ud = galsim.UniformDeviate(rng)
    max_rsq = radius*radius
    # Emulate a do-while loop
    while True:
        dx = (2*ud()-1) * radius
        dy = (2*ud()-1) * radius
        rsq = dx**2 + dy**2
        if rsq <= max_rsq:
            break
    #print 'RandomCircle: ',(dx,dy)
    return galsim.config.Shift(dx=dx,dy=dy), False

def _GenerateFromSequence(param, param_name, base, value_type):
    """@brief Return next in a sequence of integers
    """
    #print 'Start Sequence for ',param_name,' -- param = ',param
    opt = { 'first' : value_type, 'last' : value_type, 'step' : value_type, 'repeat' : int }
    ignore = { 'rep' : int, 'current' : int }
    kwargs, safe = GetAllParams(param, param_name, base, opt=opt, ignore=ignore)

    step = kwargs.get('step',1)
    first = kwargs.get('first',0)
    last = kwargs.get('last',None)
    repeat = kwargs.get('repeat',1)
    if repeat <= 0:
        raise ValueError("Invalid repeat=%d (must be > 0) for %s.type = Sequence"%(
                repeat,param_name))
    #print 'first, step, repeat = ',first,step,repeat

    if value_type is bool:
        # Then there are only really two valid sequences: Either 010101... or 101010...
        # Aside from the repeat value of course.
        if first:
            first = 1
            last = 0
            step = -1
        else:
            first = 0
            step = 1
            last = 1
        #print 'first, last, step, repeat => ',first,last,step,repeat

    rep = param.get('rep',0)
    index = param.get('current',first)
    #print 'From saved: rep = ',rep,' index = ',index
    if rep < repeat:
        rep = rep + 1
    else:
        rep = 1
        index = index + step
        if (last is not None and 
                ( (step > 0 and index > last) or
                  (step < 0 and index < last) ) ):
            index = first
    param['rep'] = rep
    param['current'] = index
    #print 'index = ',index
    #print 'saved rep,current = ',param['rep'],param['current']
    return index, False

def _GenerateFromList(param, param_name, base, value_type):
    """@brief Return next item from a provided list
    """
    req = { 'items' : list }
    opt = { 'index' : int }
    # Only Check, not Get.  We need to handle items a bit differently, since it's a list.
    CheckAllParams(param, param_name, req=req, opt=opt)
    items = param['items']
    if not isinstance(items,list):
        raise AttributeError("items entry for parameter %s is not a list."%param_name)

    # Setup the indexing sequence if it hasn't been specified using the length of items.
    SetDefaultIndex(param, len(items))
    index, safe = ParseValue(param, 'index', base, int)

    if index < 0 or index >= len(items):
        raise AttributeError("index %d out of bounds for parameter %s"%(index,param_name))
    val, safe1 = ParseValue(items, index, base, value_type)
    safe = safe and safe1
    return val, safe
 
def SetDefaultIndex(config, num):
    """
    When the number of items in a list is known, we allow the user to omit some of 
    the parameters of a Sequence or Random and set them automatically based on the 
    size of the list, catalog, etc.
    """
    if 'index' not in config:
        config['index'] = { 'type' : 'Sequence', 'last' : num-1 }
    elif isinstance(config['index'],dict) and 'type' in config['index'] :
        index = config['index']
        type = index['type']
        if ( type == 'Sequence' and 
             ('step' not in index or (isinstance(index['step'],int) and index['step'] > 0) ) and
             'last' not in index ):
            index['last'] = num-1
        elif ( type == 'Sequence' and 
             ('step' in index and (isinstance(index['step'],int) and index['step'] < 0) ) ):
            if 'first' not in index:
                index['first'] = num-1
            if 'last' not in index:
                index['last'] = 0
        elif type == 'Random' and 'max' not in index:
            index['max'] = num-1
