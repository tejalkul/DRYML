# File to define saving/loading convenience functions

from __future__ import annotations

import os
import dill
import pickle
import io
import zipfile
import uuid
from typing import IO, Union, Optional, Type
from dryml.dry_config import DryKwargs, DryArgs, DryObjectDef
from dryml.utils import init_arg_list_handler, init_arg_dict_handler, \
    get_current_cls, pickler, static_var

FileType = Union[str, IO[bytes]]


def file_resolve(file: str, exact_path: bool = False) -> str:
    if os.path.splitext(file)[1] == '' and not exact_path:
        file = f"{file}.dry"
    return file


def load_zipfile(file: FileType, exact_path: bool = False,
                 mode='r', must_exist: bool = True) -> zipfile.ZipFile:
    if type(file) is str:
        filepath = file
        filepath = file_resolve(filepath, exact_path=exact_path)
        if must_exist and not os.path.exists(filepath):
            raise ValueError(f"File {filepath} doesn't exist!")
        file = zipfile.ZipFile(filepath, mode=mode)
    if type(file) is not zipfile.ZipFile:
        file = zipfile.ZipFile(file, mode=mode)
    return file


class DryObjectFile(object):
    def __init__(self, file: FileType, exact_path: bool = False,
                 mode: str = 'r', must_exist: bool = True):

        self.file = load_zipfile(file, exact_path=exact_path,
                                 mode=mode, must_exist=must_exist)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self.file.close()

    # def update_file(self, obj: DryObject):
    #     self.cache_object_data_obj(obj)

    def save_meta_data(self):
        # Meta_data
        meta_data = {
            'version': 1
        }

        meta_dump = pickler(meta_data)
        with self.file.open('meta_data.pkl', mode='w') as f:
            f.write(meta_dump)

    def load_meta_data(self):
        with self.file.open('meta_data.pkl', 'r') as meta_file:
            meta_data = pickle.loads(meta_file.read())
        return meta_data

    def save_class_def_v1(self, obj_def: DryObjectDef, update: bool = False):
        # We need to pickle the class definition.
        # By default, error out if class has changed. Check this.
        mod_cls = get_current_cls(obj_def.cls)
        if obj_def.cls != mod_cls and not update:
            raise ValueError("Can't save class definition! It's been changed!")
        cls_def = dill.dumps(mod_cls)
        with self.file.open('cls_def.dill', mode='w') as f:
            f.write(cls_def)

    def load_class_def_v1(self, update: bool = True, reload: bool = False):
        "Helper function for loading a version 1 class definition"
        # Get class definition
        with self.file.open('cls_def.dill') as cls_def_file:
            if update:
                # Get original model definition
                cls_def_init = dill.loads(cls_def_file.read())
                try:
                    cls_def = get_current_cls(cls_def_init, reload=reload)
                except Exception as e:
                    raise RuntimeError(f"Failed to update module class {e}")
            else:
                cls_def = dill.loads(cls_def_file.read())
        return cls_def

    def save_definition_v1(self, obj_def: DryObjectDef, update: bool = False):
        "Save object def"
        # Save obj def
        self.save_class_def_v1(obj_def, update=update)

        # Save args from object def
        with self.file.open('dry_args.pkl', mode='w') as args_file:
            args_file.write(pickler(obj_def.args.data))

        # Save kwargs from object def
        with self.file.open('dry_kwargs.pkl', mode='w') as kwargs_file:
            kwargs_file.write(pickler(obj_def.kwargs.data))

    def load_definition_v1(self, update: bool = True, reload: bool = False):
        "Load object def"

        # Load obj def
        cls = self.load_class_def_v1(update=update, reload=reload)

        # Load args
        with self.file.open('dry_args.pkl', mode='r') as args_file:
            args = pickle.loads(args_file.read())

        # Load kwargs
        with self.file.open('dry_kwargs.pkl', mode='r') as kwargs_file:
            kwargs = pickle.loads(kwargs_file.read())

        return DryObjectDef(cls, *args, **kwargs)

    def definition(self, update: bool = True, reload: bool = False):
        meta_data = self.load_meta_data()
        if meta_data['version'] == 1:
            return self.load_definition_v1(update=update, reload=reload)
        else:
            raise RuntimeError(
                f"File version {meta_data['version']} not supported!")

    def load_object_v1(self, update: bool = True,
                       reload: bool = False,
                       as_cls: Optional[Type] = None) -> DryObject:
        # Load object
        obj_def = self.load_definition_v1(update=update, reload=reload)
        if as_cls is not None:
            obj_def.cls = as_cls

        # Create object
        obj = obj_def.build()

        # Load object content
        obj.load_object_imp(self.file)

        # Build object instance
        return obj

    def load_object(self, update: bool = False,
                    reload: bool = False,
                    as_cls: Optional[Type] = None) -> DryObject:
        meta_data = self.load_meta_data()
        version = meta_data['version']
        if version == 1:
            return self.load_object_v1(
                update=update, reload=reload, as_cls=as_cls)
        else:
            raise RuntimeError(f"DRY version {version} unknown")

    def save_object_v1(self, obj: DryObject, update: bool = False,
                       as_cls: Optional[Type] = None) -> bool:
        # Save meta data
        self.save_meta_data()

        # Save config v1
        obj_def = obj.definition()
        if as_cls is not None:
            obj_def.cls = as_cls

        self.save_definition_v1(obj_def)

        # Save object content
        obj.save_object_imp(self.file)

        return True


@static_var('load_repo', None)
def load_object(file: FileType, update: bool = False,
                exact_path: bool = False,
                reload: bool = False,
                as_cls: Optional[Type] = None,
                repo=None) -> DryObject:
    """
    A method for loading an object from disk.
    """
    reset_repo = False
    load_obj = True

    # Handle repo management variables
    if repo is not None:
        if load_object.load_repo is not None:
            raise RuntimeError(
                "different repos not currently supported")
        else:
            # Set the call_repo
            load_object.load_repo = repo
            reset_repo = True

    # We now need the object definition
    with DryObjectFile(file, exact_path=exact_path) as dry_file:
        obj_def = dry_file.definition()
        # Check whether a repo was given in a prior call
        if load_object.load_repo is not None:
            try:
                # Load the object from the repo
                obj = load_object.load_repo.get_obj(obj_def)
                load_obj = False
                print("Fetched object from repo")
            except Exception as e:
                print("Failed to find object in repo")
                print(f"cat_id: {obj_def.get_category_id()}")
                print(f"ind_id: {obj_def.get_individual_id()}")
                print(f"error was: {e}")
                pass

        if load_obj:
            print("Load object from disk")
            obj = dry_file.load_object(update=update,
                                       reload=reload,
                                       as_cls=as_cls)

    # Reset the repo for this function
    if reset_repo:
        load_object.load_repo = None

    return obj


def save_object(obj: DryObject, file: FileType, version: int = 1,
                exact_path: bool = False, update: bool = False,
                as_cls: Optional[Type] = None) -> bool:
    with DryObjectFile(file, exact_path=exact_path, mode='w',
                       must_exist=False) as dry_file:
        if version == 1:
            return dry_file.save_object_v1(obj, update=update, as_cls=as_cls)
        else:
            raise ValueError(f"File version {version} unknown. Can't save!")


def change_object_cls(obj: DryObject, cls: Type, update: bool = False,
                      reload: bool = False) -> DryObject:
    buffer = io.BytesIO()
    save_object(obj, buffer)
    return load_object(buffer, update=update, reload=reload,
                       as_cls=cls)


# Define a base Dry Object
class DryObject(object):
    def __init__(self, *args, dry_args=None, dry_kwargs=None,
                 dry_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Use DryKwargs/DryArgs object to coerse args/kwargs to proper
        # json serializable form.
        self.dry_args = DryArgs(init_arg_list_handler(dry_args))
        self.dry_kwargs = DryKwargs(init_arg_dict_handler(dry_kwargs))
        # Generate unique id for this object. (Meant to separate between
        # multiple instances of same object)
        if dry_id is None:
            self.dry_kwargs['dry_id'] = str(uuid.uuid4())
        else:
            self.dry_kwargs['dry_id'] = dry_id

    def definition(self):
        return DryObjectDef(
            type(self),
            *self.dry_args,
            **self.dry_kwargs)

    def load_object_imp(self, file: zipfile.ZipFile) -> bool:
        # Should be the last object inherited
        return True

    def save_object_imp(self, file: zipfile.ZipFile) -> bool:
        # Should be the last object inherited
        return True

    def save_self(self, file: FileType, version: int = 1, **kwargs) -> bool:
        return save_object(self, file, version=version, **kwargs)


class DryObjectFactory(object):
    def __init__(self, obj_def: DryObjectDef, callbacks=[]):
        if 'dry_id' in obj_def:
            raise ValueError(
                "An Object factory can't use a definition with a dry_id")
        self.obj_def = obj_def
        self.callbacks = callbacks

    def add_callback(self, callback):
        self.callbacks.append(callback)

    def __call__(self):
        obj = self.obj_def.build()
        for callback in self.callbacks:
            # Call each callback
            callback(obj)
        return obj
