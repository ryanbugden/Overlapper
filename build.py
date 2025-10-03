# -----------------
# Extension Details
# -----------------

name                = "Overlapper"
version             = "2.1.2"
developer           = "Ryan Bugden"
developer_url       = "https://ryanbugden.com"
rf_version          = "4.4"
pyc_only            = False
menu_items          = [
                        dict(
                            nestInSubmenus=True,
                            path="settings.py",
                            preferredName="Settings...",
                            shortKey="")
                        ]
main_script         = "overlapper.py"
icon_file           = "_images/mechanic_icon.png"
launch_at_startup   = True
install_after_build = True

# ----------------------
# Don't edit below here.
# ----------------------

from AppKit import *
import os
import shutil
from mojo.extensions import ExtensionBundle

# Convert short key modifiers.

modifier_map = {
    "command": NSCommandKeyMask,
    "control": NSControlKeyMask,
    "option": NSAlternateKeyMask,
    "shift": NSShiftKeyMask,
    "capslock": NSAlphaShiftKeyMask,
}

for menu_item in menu_items:
    short_key = menu_item.get("shortKey")
    if isinstance(short_key, tuple):
        short_key = list(short_key)
        character = short_key.pop(0)
        converted = None
        for modifier in short_key:
            modifier = modifier_map.get(modifier)
            if converted is None:
                converted = modifier
            else:
                converted |= modifier
        short_key = (converted, character)
        menu_item["short_key"] = short_key

# Make the various paths.
base_path = os.path.dirname(__file__)
source_path = os.path.join(base_path, "source")
lib_path = os.path.join(source_path, "lib")
license_path = os.path.join(base_path, "license.txt")
requirements_path = os.path.join(base_path, "requirements.txt")
resources_path = os.path.join(source_path, "resources")
if not os.path.exists(resources_path):
    resources_path = None
extension_file = "%s.roboFontExt" % name
build_path = base_path
extension_path = os.path.join(build_path, extension_file)

# Build the extension.
B = ExtensionBundle()
B.name = name
B.developer = developer
B.developerURL = developer_url
B.version = version
B.icon = icon_file
B.launchAtStartUp = launch_at_startup
B.mainScript = main_script
doc_path = os.path.join(source_path, "documentation")
has_docs = False
if os.path.exists(os.path.join(doc_path, "index.html")):
    has_docs = True
elif os.path.exists(os.path.join(doc_path, "index.md")):
    has_docs = True
    shutil.copy(os.path.join(doc_path, "index.md"), os.path.join(base_path, "README.md"))
    base_images_path = os.path.join(base_path, "_images")
    doc_images_path = os.path.join(doc_path, "_images")
    for item in os.listdir(doc_images_path):
        shutil.copy(os.path.join(doc_images_path, item), os.path.join(base_images_path, item))
    # Remove from base folder if not in the source folder.
    for item in os.listdir(base_images_path):
        if item not in os.listdir(doc_images_path):
            os.remove(os.path.join(base_images_path, item))
if not has_docs:
    doc_path = None
B.html = has_docs
B.requiresVersionMajor = rf_version.split(".")[0]
B.requiresVersionMinor = rf_version.split(".")[1]
B.addToMenu = menu_items
with open(license_path) as license:
    B.license = license.read()
if os.path.exists(requirements_path):
    with open(requirements_path) as requirements:
        B.requirements = requirements.read()
print("Building extension...", end=" ")
v = B.save(extension_path, libPath=lib_path, pycOnly=pyc_only, htmlPath=doc_path, resourcesPath=resources_path)
print("done!")
errors = B.validationErrors()
if errors:
    print("There were errors:")
    print(errors)

# Install the extension.

if install_after_build:
    print("Installing extension...", end=" ")
    install_dir = os.path.expanduser(f"~/Library/Application Support/RoboFont/plugins")
    install_path = os.path.join(install_dir, extension_file)
    if os.path.exists(install_path):
        shutil.rmtree(install_path)
    shutil.copytree(extension_path, install_path)
    print("Done!")
    print("RoboFont must now be restarted.")
