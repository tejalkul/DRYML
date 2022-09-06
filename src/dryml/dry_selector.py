from dryml.dry_object import DryObject, DryObjectFile, DryObjectDef
from dryml.utils import is_nonstring_iterable, is_dictlike, get_class_str, \
    is_supported_scalar_type, is_supported_dictlike, is_supported_listlike, \
    map_dictlike, map_listlike
from typing import Union, Callable, Type, Mapping


# Need to recursively build selector when applied to a dictionary
def def_to_sel(val, cache=None):
    def applier(val):
        return def_to_sel(val, cache=cache)
    if is_supported_scalar_type(val):
        return val
    elif isinstance(val, DryObject):
        return DrySelector.from_def(val.definition(), cache=cache)
    elif isinstance(val, DryObjectDef):
        return DrySelector.from_def(val, cache=cache)
    elif is_supported_listlike(val):
        return map_listlike(applier, val)
    elif is_supported_dictlike(val):
        return map_dictlike(applier, val)
    else:
        raise RuntimeError(
            f"Encountered unsupported value {val} of type {type(val)}")


class DrySelector(object):
    "Utility object for selecting for specific dry objects"

    @staticmethod
    def from_def(
            obj_def: DryObjectDef,
            cache=None):

        # Create the cache if needed
        if cache is None:
            cache = {}

        # check the cache
        def_id = id(obj_def)
        if def_id in cache:
            return cache[def_id]

        new_args = def_to_sel(
            obj_def['dry_args'],
            cache=cache)

        new_kwargs = def_to_sel(
            obj_def['dry_kwargs'],
            cache=cache)

        sel = DrySelector(
            obj_def['cls'],
            args=new_args,
            kwargs=new_kwargs)

        cache[def_id] = sel

        return sel

    @staticmethod
    def from_dict(
            obj_dict: Mapping):
        raise RuntimeError("Functionality Questionable")
        args = obj_dict.get('dry_args', ())
        kwargs = obj_dict.get('dry_kwargs', {})
        return DrySelector(
            obj_dict['cls'],
            args=args,
            kwargs=kwargs)

    @staticmethod
    def from_obj(
            obj: DryObject):
        return DrySelector.from_def(
            obj.definition())

    @staticmethod
    def build(
            obj):
        if isinstance(obj, DryObject):
            return DrySelector.from_obj(obj)
        elif isinstance(obj, DryObjectDef):
            return DrySelector.from_def(obj)
        elif isinstance(obj, Mapping):
            return DrySelector.from_dict(obj)
        else:
            raise TypeError(
                f"Can't construct DrySelector from type {type(obj)}")

    def __init__(self, cls: Type, args=None, kwargs=None):
        self.cls = cls
        self.args = args
        self.kwargs = kwargs

    @staticmethod
    def match_objects(
            key_object, value_object, verbosity=0, cls_str_compare=True):
        if issubclass(type(key_object), type):
            # We have a type object. They match if
            res = issubclass(value_object, key_object)
            if not res and verbosity > 1:
                print(f"{value_object} is not a subclass of {key_object}")
            return res
        elif isinstance(key_object, DrySelector):
            res = key_object(
                value_object,
                verbosity=verbosity,
                cls_str_compare=cls_str_compare)
            if not res and verbosity > 1:
                print(f"{value_object} did not satisfy selector {key_object}")
            return res
        elif callable(key_object):
            res = key_object(value_object)
            if not res and verbosity > 1:
                print(f"callable on {value_object} failed.")
            return res
        elif isinstance(key_object, DryObjectDef):
            return key_object.equal(
                value_object, cls_str_compare=cls_str_compare)
        elif isinstance(value_object, DryObjectDef):
            return value_object.equal(
                key_object, cls_str_compare=cls_str_compare)
        elif is_dictlike(key_object):
            # dictlike branch is first because dictlike objects
            # are also iterable objects
            if not is_dictlike(value_object):
                if verbosity > 0:
                    print(f"a dict-like key object {key_object} not matched "
                          f"up with a dict-like value object {value_object}.")
                return False
            for key in key_object:
                if key not in value_object:
                    if verbosity > 0:
                        print(f"didn't find expected key {key} in "
                              f"{value_object}")
                    return False
                print(f"// dictlike key: {key}")
                if not DrySelector.match_objects(
                        key_object[key],
                        value_object[key],
                        verbosity=verbosity,
                        cls_str_compare=cls_str_compare):
                    return False
        elif is_nonstring_iterable(key_object):
            if not is_nonstring_iterable(value_object):
                if verbosity > 0:
                    print(f"expected a nonstring iterable, got {value_object}")
                return False
            # For now, lists must have the same number of elements
            if len(key_object) != len(value_object):
                if verbosity > 0:
                    print("key object and value object have different "
                          f"lengths. expected {len(key_object)} got "
                          f"{len(value_object)}")
                return False
            for i in range(len(key_object)):
                # Each object must match
                if not DrySelector.match_objects(
                        key_object[i],
                        value_object[i],
                        verbosity=verbosity,
                        cls_str_compare=cls_str_compare):
                    return False
        else:
            if key_object != value_object:
                if verbosity > 0:
                    print(f"expected {key_object}, got {value_object}")
                return False

        return True

    def cls_compare(self, matcher, cls, verbosity=0, cls_str_compare=True):
        matched = True
        if isinstance(matcher, type):
            if not issubclass(cls, matcher):
                matched = False
        elif isinstance(matcher, Callable):
            if not matcher(cls):
                matched = False
        elif isinstance(matcher, str):
            if matcher != get_class_str(cls):
                matched = False
        else:
            raise ValueError(f"Unsupported matcher type: {type(matcher)}")
        if not matched:
            # Failure message
            if verbosity > 0:
                print("Class doesn't match")
            if verbosity > 1:
                print(f"Got {cls}, matcher: {matcher}")
            return False
        else:
            return True

    def args_compare(self, matcher, args, verbosity=0):
        if DrySelector.match_objects(matcher, args,
                                     verbosity=verbosity):
            return True
        else:
            if verbosity > 0:
                print("Args don't match")
            if verbosity > 1:
                print(f"Got {args}, matcher: {matcher}")
            return False

    def kwargs_compare(self, matcher, kwargs, verbosity=0):
        if DrySelector.match_objects(matcher, kwargs,
                                     verbosity=verbosity):
            return True
        else:
            if verbosity > 0:
                print("Kwargs don't match")
            if verbosity > 1:
                print(f"Got {kwargs}, matcher: {matcher}")
            return False

    def __call__(
            self,
            obj: Union[DryObject, DryObjectFile, DryObjectDef, Mapping],
            verbosity=0,
            cls_str_compare=True):
        if verbosity > 0:
            print(f"====== Selection started ({id(self)}) ({self.cls}) ======")
            if verbosity > 1:
                print(f"matching obj: {obj}")
        # Get definition
        if isinstance(obj, DryObjectDef):
            obj_def = obj
        elif isinstance(obj, DryObject) or isinstance(obj, DryObjectFile):
            obj_def = obj.definition()
        elif isinstance(obj, Mapping):
            raise RuntimeError("Not currently supported")
        else:
            if verbosity > 0:
                print(
                    f"input object not a matchable object. type: {type(obj)}")
            return False

        # If required, check object class
        if self.cls is not None:
            if not self.cls_compare(
                    self.cls,
                    obj_def.cls,
                    verbosity=verbosity,
                    cls_str_compare=cls_str_compare):
                if verbosity > 0:
                    print("Class didn't match")
                if verbosity > 1:
                    print(f"Expected class {self.cls} got {obj_def.cls}")
                return False

        # Check object args
        if self.args is not None:
            if not self.args_compare(
                    self.args,
                    obj_def.args,
                    verbosity=verbosity):
                if verbosity > 0:
                    print("Args didn't match")
                if verbosity > 1:
                    print(f"Expected args {self.args} got {obj_def.args}")
                return False

        # Check object kwargs
        if self.kwargs is not None:
            if not self.kwargs_compare(
                    self.kwargs,
                    obj_def.kwargs,
                    verbosity=verbosity):
                if verbosity > 0:
                    print("Kwargs didn't match")
                if verbosity > 1:
                    print(f"Expected kwargs {self.kwargs} "
                          f"got {obj_def.kwargs}")
                return False

        return True

    def __str__(self):
        return f"DrySelector({self.cls}, {self.args}, {self.kwargs})"

    def repr(self):
        return f"{self}"
