import os
import subprocess
import sys
import multiprocessing
import argparse
import shutil
import getpass
import concurrent.futures
from tqdm import tqdm
from datetime import datetime
import re

def parse_arguments():
    def dir_path(path):
        if os.path.isdir(path) and path != None:
            return path
        else:
            raise argparse.ArgumentTypeError(f"readable_dir:{path} is not a valid path")
    
    class thread_count:
        def __init__(self, string):
            self._val = int(string)
            max_threads = multiprocessing.cpu_count()
            if not 0 < self._val <= max_threads:
                raise argparse.ArgumentTypeError(f"Invalid thread count, supply a value between 1 and {max_threads}")
        def __int__(self):
            return self._val
        
    parser = argparse.ArgumentParser(description='Scan for .flac files in subdirectories, recompress them and optionally calculate replay gain tags.')
    parser.add_argument('-d', '--directory',
                        help='The directory that will be recursively scanned for .lrc and .txt files.', type=dir_path, default=".", const=".", nargs="?")
    parser.add_argument('-j', action='store_true',
                        help='flac >=1.5.0: Encode 1 file at a time with multi-threading (threadcount specified via -m) instead of encoding multiple files concurrently.')
    parser.add_argument('-l', '--log', action='count',
                        help='Log errors during recompression or testing to flacr.log.')
    parser.add_argument('-m', '--multi_threaded', type=thread_count, default=1, const=1, nargs="?",
                        help='The number of threads used during conversion and replay gain calculation, default: 1.')
    parser.add_argument('-p', '--progress', action='store_true',
                        help='Show progress bars during scanning/recompression/testing. Useful for huge directories. Requires tqdm, use "pip3 install tqdm" to install it.')
    parser.add_argument('-r', '--rsgain', action='store_true',
                        help='Calculate replay gain values with rsgain and save them in the audio file tags.')
    parser.add_argument('-s', '--single_folder', action='store_true',
                        help='Only scan the current folder for flac files to recompress, no subdirectories.')
    parser.add_argument('-t', '--test', action='store_true',
                        help='Skip recompression and only log decoding errors to console or log when used with -l.')
    parser.add_argument('-Q', '--quick', action='store_true',
                        help='Equal to using -m with the max available threadcount, -r to calculate replay gain values and -p to display a progress bar.')
    parser.add_argument('-S', '--sequential', action='store_true',
                        help='Equal to using -m 4 -j to encode 1 file at a time with 4 threads, -r to calculate replay gain values and -p to display a progress bar.')

    args: argparse.Namespace = parser.parse_args()

    if args.quick or args.sequential:
        setattr(args, "rsgain", True)
        setattr(args, "progress", True)
    if args.quick:
        setattr(args, "multi_threaded", multiprocessing.cpu_count())
    if args.sequential:
        setattr(args, "multi_threaded", (4 if 4 <= multiprocessing.cpu_count() else multiprocessing.cpu_count()))
        setattr(args, "j", True)
 
    return args

def find_flac_files(directory, single_folder, progress):
    flac_files = []
    if not single_folder:
        with tqdm(desc="searching", unit=" files", disable=not progress, ncols=100) as pbar:
            flac_count = 0
            for root, dirs, files in os.walk(directory):
                for file in files:
                    pbar.update(1)
                    if file.endswith(".flac"):
                        flac_files.append(os.path.join(os.path.abspath(root), file))
                        flac_count += 1
                        pbar.set_postfix({"flac files": flac_count})
    else:
        with tqdm(desc="searching", unit=" files", disable=not progress, ncols=100) as pbar:
            flac_count = 0
            for file in os.listdir(directory):
                if file.endswith(".flac"):
                    flac_files.append(os.path.join(os.path.abspath(directory), file))
                    flac_count += 1
                    pbar.set_postfix({"flac files": flac_count})
    return flac_files
    
def verify_flac(file_path):
    # Define the verify command
    command = ["flac", "-t", "--silent", file_path]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return file_path, result.stderr
    except subprocess.CalledProcessError as e:
        return file_path, e.stderr

def reencode_flac(file_path, thread_count=1):
    # Define the temporary output file path
    temp_file_path = file_path + ".tmp"

    # Define the re-encoding command
    command = ["flac", "--best", "--verify", "--padding=4096", "--silent"]

    if thread_count > 1:
        command.append(f"--threads={thread_count}")

    command.extend([file_path, "-o", temp_file_path])

    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text = True, check=True)
        if result.stderr:
            print(f"Error encountered while re-encoding {file_path}:\n{result.stderr}")
            os.remove(temp_file_path)
        else:
            # Replace the original file with the temporary file
            try:
                os.remove(file_path)
                os.rename(temp_file_path, file_path)
            except PermissionError as e:
                print(f"Could not replace {file_path} because it is locked. The temporary file remains: {temp_file_path}")
                print(f"Please close any programs using {file_path} and manually replace it with {temp_file_path}.")
                return file_path, "File locked. Manual replacement required."
        return file_path, result.stderr
    except subprocess.CalledProcessError as e:
        # If an error occurs, return the filepath and stderr
        return file_path, e.stderr

def run_rsgain(directory, thread_count):
    #set rsgain thread count to at least 2 to prevent windows cli limitations to hinder performance
    if thread_count == 1: thread_count = 2
    # Define the replay gain calculation command
    rs_gain_command = ["rsgain", "easy", "-m", str(thread_count), directory]
    try:
        subprocess.run(rs_gain_command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error while executing rsgain.\n{e}")
        sys.exit()

def write_log(error_log):
    if not os.access(".", os.W_OK | os.X_OK):
        print("Cannot write log file to current directory. Ensure that you have write permission. Skipping log creation.")
        return
    if len(error_log) > 0:
        with open(f"flacr_error.log", "a", encoding="utf8") as log:
            now = datetime.now()
            log.write(f'\nflacr error log, date: {now.strftime("%Y-%m-%d %H:%M:%S")}\n')
            for path, error in error_log:
                log.write(f"{path}\n{error}\n")

def flac_on_path():
    if shutil.which("flac") is None and sys.platform == "win32":
        choice = input("flac executable is not on PATH, open environment variable settings in Windows to add it? (y/n): ")
        if choice == "y":
            print(f"""
    Step 1: Under 'User variables for {getpass.getuser()}' select 'Path' and either double click it or click on 'Edit...'
    Step 2: Click on 'New' and paste the path to the folder on your system that contains flac.exe.
            Then confirm with "OK" twice.

            Info:
            If you do not have flac installed yet, visit this website (or download it from a source you trust):
            https://xiph.org/flac/download.html
            Then click on FLAC for Windows, select the most recent "flac-x.x.x-win.zip" file, download it and unpack it.
            You can pretty much put the folder wherever you like.
            My flac executable (as of writing) for example is located in
            C:\\Program Files (x86)\\flac-1.4.3-win\\Win64
            Once you have decided on where to store it, add that path to PATH as described above.

            Note:
            You can also add the folder that contains this script to PATH in the same way
            if you want to call it from any folder.

    Step 3: Once that is done, re-run this script.""")
            try:
                subprocess.run(["rundll32.exe", "sysdm.cpl,EditEnvironmentVariables"])
            except subprocess.CalledProcessError:
                print(f"Error opening environment variable settings.")
            sys.exit()
        else:
            print("Exiting.")
            sys.exit()
    elif shutil.which("flac") is None:
        print("flac is not on PATH, add it and try again.")
        sys.exit()
    else:
        return
    
def rsgain_on_path():
    if shutil.which("rsgain") is None and sys.platform == "win32":
        choice = input("rsgain executable is not on PATH, open environment variable settings in Windows to add it? (y/n): ")
        if choice == "y":
            print(f"""
    Step 1: Under 'User variables for {getpass.getuser()}' select 'Path' and either double click it or click on 'Edit...'
    Step 2: Click on 'New' and paste the path to the folder on your system that contains rsgain.exe.
            Then confirm with "OK" twice.

            Info:
            If you do not have flac installed yet, visit this website:
            https://github.com/complexlogic/rsgain/releases
            Then under Assets, select the most recent "rsgain-x.x-win64.zip" file, download it and unpack it.
            You can pretty much put the folder wherever you like.
            My rsgain executable (as of writing) for example is located in
            C:\\Program Files (x86)\\rsgain-3.5-win64
            Once you have decided on where to store it, add that path to PATH as described above.

            Note:
            You can also add the folder that contains this script to PATH in the same way
            if you want to call it from any folder.

    Step 3: Once that is done, re-run this script.""")
            try:
                subprocess.run(["rundll32.exe", "sysdm.cpl,EditEnvironmentVariables"])
            except subprocess.CalledProcessError:
                print(f"Error opening environment variable settings.")
            sys.exit()
        else:
            print("Exiting.")
            sys.exit()
    elif shutil.which("rsgain") is None:
        print("rsgain is not on PATH, add it to PATH or execute the program again without -r.")
        sys.exit()
    else:
        return True

def flac_version_check():
    min_version_pattern = r'^flac (?:(1\.(?:[5-9]|1[0-9])\.\d+)|((2\.\d+\.\d+)))$'
    flac_version = subprocess.run(["flac", "--version"], encoding='utf-8', stdout=subprocess.PIPE)
    # Check if the flac version is >=1.5.0 as multi-threading is not available in earlier versions
    if re.match(min_version_pattern, flac_version.stdout):
        return
    else:
        print (f"The installed flac version: {flac_version.stdout.strip()} does not support multi-threading. Install v1.5.0 or later or rerun without -j.")
        sys.exit()

def main(args):
    args = parse_arguments()
    directory = args.directory
    log_to_disk = args.log
    thread_count = int(args.multi_threaded)
    progress = args.progress
    calc_rsgain = args.rsgain
    single_folder = args.single_folder
    test_run = args.test
    multi_threaded = args.j

    # Check if flac executable is available on PATH and abort if it is not.
    flac_on_path()

    if calc_rsgain:
        # Check if rsgain executable is available on PATH and abort if it is not.
        calc_rsgain = rsgain_on_path()

    # Collect paths of all .flac files
    flac_files = find_flac_files(directory, single_folder, progress)
    error_log = []
    error_count = 0

    # Calculate replay gain values and write them to the tags
    if calc_rsgain:
        run_rsgain(directory, thread_count)

    if not test_run:
        # Encode files 1 at a time with multiple threads
        if multi_threaded:
            flac_version_check()
            with tqdm(total=len(flac_files), desc="encoding", unit="files", disable=not progress, ncols=100) as pbar:
                for flac_file in flac_files:
                    filepath, stderr = reencode_flac(flac_file, thread_count)
                    if stderr:
                        error_log.append((filepath, stderr))
                        error_count += 1
                        pbar.set_postfix({"errors": error_count})
                    pbar.update(1)
        # Encode multiple files concurrently
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
                # Submit tasks to the executor
                futures = {executor.submit(reencode_flac, filepath): filepath for filepath in flac_files}
                
                # Track progress using tqdm
                with tqdm(total=len(flac_files), desc="encoding", unit=" files", disable=not progress, ncols=100) as pbar:
                    for future in concurrent.futures.as_completed(futures):
                        filepath, stderr = future.result()
                        if stderr:
                            error_log.append((filepath, stderr))
                            error_count += 1
                            pbar.set_postfix({"errors": error_count})
                        pbar.update(1)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
            # Submit tasks to the executor
            futures = {executor.submit(verify_flac, filepath): filepath for filepath in flac_files}

            # Track progress using tqdm
            with tqdm(total=len(flac_files), desc="verifying", unit=" files", disable=not progress, ncols=100) as pbar:
                for future in concurrent.futures.as_completed(futures):
                    filepath, stderr = future.result()
                    if stderr:
                        error_log.append((filepath, stderr))
                        error_count += 1
                        pbar.set_postfix({"errors": error_count})
                    pbar.update(1)
    
    if log_to_disk:
        write_log(error_log)
    else:
        for path, error in error_log:
            print (f"Encountered error when processing file:\n{path}\n{error}")
    percentage = (error_count / len(flac_files)) * 100 if len(flac_files) > 0 else 0
    print(f"\n{len(flac_files)} flac files processed, {error_count} errors. Error rate: {percentage:.2f} %.")

if __name__ == "__main__":
    args = parse_arguments()
    try:
        main(args)
    except KeyboardInterrupt:
        print("Interrupted")
        try:
            sys.exit(130)
        except SystemExit:
            os._exit(130)