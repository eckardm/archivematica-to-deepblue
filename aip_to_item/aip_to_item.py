import os
import shutil
import subprocess

# `\media\sf_DeepBlue` is auto-mounted
staging_dir = os.path.join(os.path.sep, "media", "sf_DeepBlue", "deepblue_saf_staging")
temp_dir = os.path.join(os.path.sep, "media", "sf_DeepBlue", "deepblue_saf_temp")

for root, _, files in os.walk(staging_dir):
    for name in files:

        aip = os.path.join(root, name)

        # make working copy
        shutil.copy(aip, temp_dir)

        aip = os.path.join(temp_dir, name)

        # unarchive aips
        command = [
            "unar",
            "-force-overwrite",
            "-output-directory", temp_dir,
            aip
        ]
        subprocess.call(command)

        os.remove(aip)

        aip_dir = os.path.join(temp_dir, os.path.splitext(aip)[0])
