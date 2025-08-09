import fractale.utils as utils
import shutil
import os
import re
import tempfile
import collections

def get_context(context):
    """
    Get or create the context.
    """
    if isinstance(context, Context):
        return context
    return Context(context)


class Context(collections.UserDict):
    """
    A custom dictionary that allows attribute-style access to keys,
    and extends the 'get' method with a 'required' argument.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs) 

        # Testing out this idea - instead of requiring specific inputs/outputs, we are going
        # to write to a common context directory, and allow each LLM to discover files and use them
        # as needed.
        workspace = kwargs.get("workspace")
        self.workspace = workspace or tempfile.mkdtemp()

    def __getattribute__(self, name):
        """
        Intercepts all attribute lookups (including methods/functions)
        """        
        try:
            # Step 1: this would be a normal attribute
            attr = object.__getattribute__(self, name)
        except AttributeError:
            # Then handle lookup of dict key by attribute
            return super().__getattribute__(name)

        # Step 2: We allow "get" to be called with defaults / required.
        if name == 'get':
            original_get = attr

            def custom_get(key, default=None, required=False):
                """
                Wrapper for the standard dict.get() method.
                Accepts the custom 'required' argument.
                """
                # Load context if needed
                self.load(key)

                if required:
                    if key not in self.data:
                        raise KeyError(f"Key '{key}' is required but missing.")

                    # If required and found, just return the value
                    return self.data[key]
                else:
                    # If not required, use the original dict.get behavior
                    return original_get(key, default)

            # Return the wrapper function instead of the original method
            return custom_get
        
        # 4. For any other attribute (like keys(), items(), update(), or custom methods)
        # return the attribute we found earlier
        return attr

    # 5. Override __getattr__ to handle attribute-style access to dictionary keys
    def __getattr__(self, name):
        """
        Allows access to dictionary keys as attributes.
        """
        if name in self.data:
            return self.data[name]        
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
        
    def __setattr__(self, name, value):
        """
        Allows setting keys via attribute assignment.
        """
        # If the attribute name is a reserved name (like 'data'), set it normally
        if name in ('data', '_data'):
            super().__setattr__(name, value)
        
        # Otherwise, treat it as a dictionary key
        else:
            self.data[name] = value

    def load(self, key):
        """
        Load the entire context. We assume that text content has already been added
        to the variable context.
        """
        context_dir = os.path.join(self.workspace, key)
        if not os.path.exists(context_dir):
            return

        # content must only include one file for now
        fullpaths = os.listdir(context_dir)
        if not fullpaths:
            return
        fullpath = os.path.join(context_dir, fullpaths[0])
        content = self.read_file(fullpath)
        self.data[key] = content
        return content

    def load_all(self):
        """
        Load the entire context. We assume that text content has already been added
        to the variable context.
        """
        for key in os.listdir(self.workspace):
            context_dir = os.path.join(self.workspace, key)
            # content must only include one file for now
            fullpaths = os.listdir(context_dir)
            if not fullpaths:
                continue
            fullpath = os.path.join(context_dir, fullpaths[0])
            self.context[key] = self.read_file(fullpath)
                
    def read_file(self, filename):
        """
        Read the full file name
        """
        if filename.endswith('json'):
            return utils.read_json(filename)
        elif re.search("(yaml|yml)$", filename):
            return utils.read_yaml(filename)
        return utils.read_file(filename)
        
    def save(self, name, content, filename):
        """
        Save content to the context. The filename should be a relative path.
        Objects will be stored akin to a simple kvs like:
        
        ./<context>/
          <key>/Dockerfile
        
        Right now we are going to assume that any file that isn't .json/yaml
        will be loaded as text. The relative path of the file is meaningful. If
        we need extended metadata we can add a metadata.json.
        """
        context_dir = os.path.join(self.workspace, name)
        if not os.path.exists(context_dir):
            os.makedirs(context_dir)
        context_file = os.path.join(context_dir, filename)
        utils.save_file(content, context_file)

    def cleanup(self):
        """
        Cleanup the context if not done yet.
        
        To start, let's make the default cleanup and we can reverse when
        we move out of development.
        """
        if self.context.get('keep') is None:
            shutil.rmtree(self.workspace, ignore_errors=True)
