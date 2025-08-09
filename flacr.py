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

# ANSI color codes for the compression report
CYAN = '\033[96m'
YELLOW = '\033[93m'
GREEN = '\033[92m'
RED = '\033[91m'
BOLD = '\033[1m'
RESET = '\033[0m'

def human_readable_size(size_bytes):
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.2f} {size_names[i]}"

def parse_arguments():
    def dir_path(path):
                                                                       
        abs_path = os.path.abspath(path)
        if os.path.isdir(abs_path) and os.access(abs_path, os.R_OK):
            return abs_path
        else:
            raise argparse.ArgumentTypeError(f"Directory not accessible: {path}")

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
                        help='The directory that will be recursively scanned for .flac files.', type=dir_path, default=".", const=".", nargs="?")
    parser.add_argument('-j', action='store_true',
                        help='flac >=1.5.0: Encode 1 file at a time with multi-threading (threadcount specified via -m) instead of encoding multiple files concurrently.')
    parser.add_argument('-l', '--log', action='store_true',
                        help='Log errors during recompression or testing to flacr.log.')
    parser.add_argument('-m', '--multi_threaded', type=thread_count, default=1, const=1, nargs="?",
                        help='The number of threads used during conversion and replay gain calculation, default: 1.')
    parser.add_argument('-p', '--progress', action='store_true',
                        help='Show progress bars during scanning/recompression/testing. Useful for large directories. Requires tqdm, use "pip3 install tqdm" to install it.')
    parser.add_argument('-r', '--rsgain', action='store_true',
                        help='Calculate replay gain values with rsgain and save them in the audio file tags.')
    parser.add_argument('-s', '--single_folder', action='store_true',
                        help='Only scan the current folder for flac files to recompress, no subdirectories.')
    parser.add_argument('-t', '--test', action='store_true',
                        help='Skip recompression and only log decoding errors to console or log when used with -l.')
    parser.add_argument('-Q', '--quick', action='store_true',
                        help='Equivalent to using -m with the max available threadcount, -r to calculate replay gain values and -p to display a progress bar.')
    parser.add_argument('-S', '--sequential', action='store_true',
                        help='Equivalent to using -m 4 -j to encode 1 file at a time with 4 threads, -r to calculate replay gain values and -p to display a progress bar.')

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
                    if file.lower().endswith(".flac"):
                        filepath = os.path.join(root, file)
                        if os.path.isfile(filepath) and os.access(filepath, os.R_OK):
                            flac_files.append(filepath)
                            flac_count += 1
                            pbar.set_postfix({"flac files": flac_count})
    else:
        with tqdm(desc="searching", unit=" files", disable=not progress, ncols=100) as pbar:
            flac_count = 0
            for file in os.listdir(directory):
                if file.lower().endswith(".flac"):
                    filepath = os.path.join(directory, file)
                    if os.path.isfile(filepath) and os.access(filepath, os.R_OK):
                        flac_files.append(filepath)
                        flac_count += 1
                        pbar.set_postfix({"flac files": flac_count})
    return flac_files

def verify_flac(file_path):
                               
    command = ["flac", "-t", "--silent", file_path]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True, timeout=300)
        return file_path, result.stderr, None, None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        return file_path, getattr(e, 'stderr', str(e)), None, None

def reencode_flac(file_path, thread_count=1):
                                           
    original_size = os.path.getsize(file_path)
    
                                           
    temp_file_path = file_path + ".tmp"

                                    
    command = ["flac", "--best", "--verify", "--padding=4096", "--silent"]

    if thread_count > 1:
        command.append(f"--threads={thread_count}")

    command.extend([file_path, "-o", temp_file_path])

    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True, timeout=1800)
        if result.stderr:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            return file_path, result.stderr, original_size, original_size
        else:
                                                
            new_size = os.path.getsize(temp_file_path)

                                                               
            try:
                os.remove(file_path)
                os.rename(temp_file_path, file_path)
            except PermissionError as e:
                print(f"Could not replace {file_path} because it is locked. The temporary file remains: {temp_file_path}")
                                                                                                                    
                return file_path, "File locked. Manual replacement required.", original_size, original_size
        return file_path, result.stderr, original_size, new_size
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        return file_path, getattr(e, 'stderr', str(e)), original_size, original_size

def run_rsgain(directory, thread_count):
                                                                                                   
    if thread_count == 1:
        thread_count = 2
    rs_gain_command = ["rsgain", "easy", "-m", str(thread_count), directory]
    try:
        subprocess.run(rs_gain_command, check=True, timeout=3600)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"Error while executing rsgain: {e}")
        return False

def write_log(error_log):
    if not error_log:
        return

    if not os.access(".", os.W_OK | os.X_OK):
        print("Cannot write log file to current directory. Ensure that you have write permission. Skipping log creation.")
        return

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
    Step 2: Click on 'New' and paste the FOLDER PATH that contains flac.exe (not the .exe file itself).
            Example: If flac.exe is in "C:\\Tools\\flac\\Win64\\flac.exe",
            then add: "C:\\Tools\\flac\\Win64"
            Then confirm with "OK" twice.

            Download Info:
            If you don't have FLAC installed yet, visit: https://xiph.org/flac/download.html
            • Click on "FLAC for Windows"
            • Download the latest "flac-x.x.x-win.zip" file
            • Extract it anywhere you prefer (e.g., C:\\Tools\\flac-1.5.0-win)
            • Use the Win64 folder path for 64-bit systems: C:\\Tools\\flac-1.5.0-win\\Win64

            Tip: You can also add this script's folder to PATH to run it from anywhere.

    Step 3: Once PATH is updated, restart this script.""")
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
    Step 2: Click on 'New' and paste the FOLDER PATH that contains rsgain.exe (not the .exe file itself).
            Example: If rsgain.exe is in "C:\\Tools\\rsgain\\rsgain.exe",
            then add: "C:\\Tools\\rsgain"
            Then confirm with "OK" twice.

            Download Info:
            If you don't have rsgain installed yet, visit: https://github.com/complexlogic/rsgain/releases
            • Under "Assets", download the latest "rsgain-x.x-win64.zip" file
            • Extract it anywhere you prefer (e.g., C:\\Tools\\rsgain-3.6-win64)
            • Add the main folder path to PATH: C:\\Tools\\rsgain-3.6-win64

            Tip: You can also add this script's folder to PATH to run it from anywhere.

    Step 3: Once PATH is updated, restart this script.""")
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
    version_pattern = r'^flac 1\.([5-9]|\d{2,})\.\d+|^flac [2-9]\.\d+\.\d+'
    try:
        flac_version = subprocess.run(["flac", "--version"], encoding='utf-8', stdout=subprocess.PIPE, timeout=10)
                                                                                                  
        if re.search(version_pattern, flac_version.stdout):
            return
        else:
            print(f"The installed flac version: {flac_version.stdout.strip()} does not support multi-threading. Install v1.5.0 or later or rerun without -j.")
            sys.exit()
    except subprocess.TimeoutExpired:
        print("Could not determine FLAC version.")
        sys.exit()

def main():
    args = parse_arguments()
    directory = args.directory
    log_to_disk = args.log
    thread_count = int(args.multi_threaded)
    progress = args.progress
    calc_rsgain = args.rsgain
    single_folder = args.single_folder
    test_run = args.test
    multi_threaded = args.j

                                                                           
    flac_on_path()

    if calc_rsgain:
                                                                                 
        calc_rsgain = rsgain_on_path()

                                      
    flac_files = find_flac_files(directory, single_folder, progress)
    error_log = []
    error_count = 0
    size_stats = []

                                                             
                   
                                           

    if not test_run:
                                                        
        if multi_threaded:
            flac_version_check()
            with tqdm(total=len(flac_files), desc="encoding", unit="files", disable=not progress, ncols=100) as pbar:
                for flac_file in flac_files:
                    filepath, stderr, original_size, new_size = reencode_flac(flac_file, thread_count)
                    size_stats.append((original_size, new_size))
                    if stderr:
                        error_log.append((filepath, stderr))
                        error_count += 1
                        pbar.set_postfix({"errors": error_count})
                    pbar.update(1)
                                            
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
                                              
                futures = {executor.submit(reencode_flac, filepath): filepath for filepath in flac_files}

                                           
                with tqdm(total=len(flac_files), desc="encoding", unit=" files", disable=not progress, ncols=100) as pbar:
                    for future in concurrent.futures.as_completed(futures):
                        filepath, stderr, original_size, new_size = future.result()
                        size_stats.append((original_size, new_size))
                        if stderr:
                            error_log.append((filepath, stderr))
                            error_count += 1
                            pbar.set_postfix({"errors": error_count})
                        pbar.update(1)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
                                          
            futures = {executor.submit(verify_flac, filepath): filepath for filepath in flac_files}

                                       
            with tqdm(total=len(flac_files), desc="verifying", unit=" files", disable=not progress, ncols=100) as pbar:
                for future in concurrent.futures.as_completed(futures):
                    filepath, stderr, _, _ = future.result()
                    if stderr:
                        error_log.append((filepath, stderr))
                        error_count += 1
                        pbar.set_postfix({"errors": error_count})
                    pbar.update(1)

    # Calculate replay gain AFTER recompression
    if calc_rsgain and not test_run and not error_log:
        print("Calculating replay gain...")
        run_rsgain(directory, thread_count)

    if log_to_disk:
        write_log(error_log)
    else:
        for path, error in error_log:
            print(f"Encountered error when processing file:\n{path}\n{error}")

    percentage = (error_count / len(flac_files)) * 100 if len(flac_files) > 0 else 0

    if error_count > 0:
        print(f"\n{RED}{BOLD}{len(flac_files)} flac files processed, {error_count} errors. Error rate: {percentage:.2f}%{RESET}")
    else:
        print(f"\n{len(flac_files)} flac files processed, {error_count} errors. Error rate: {percentage:.2f}%.")

    # Display compression statistics for non-test runs
    if not test_run and size_stats:
        original_total = sum(before for before, after in size_stats)
        new_total = sum(after for before, after in size_stats)
        saved = original_total - new_total
        percent_saved = (saved / original_total) * 100 if original_total > 0 else 0

        print(f"\n{CYAN}{BOLD}══════════════════ FLAC Compression Report ══════════════════{RESET}")
        print(f"{YELLOW}Original size:   {CYAN}{human_readable_size(original_total):<15}{RESET}")
        print(f"{YELLOW}Compressed size: {CYAN}{human_readable_size(new_total):<15}{RESET}")
        print(f"{YELLOW}Space saved:     {GREEN}{human_readable_size(saved):<15} ({percent_saved:.2f}%){RESET}")
        print(f"{CYAN}{BOLD}═════════════════════════════════════════════════════════════{RESET}\n")

if __name__ == "__main__":
                            
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted")
        try:
            sys.exit(130)
        except SystemExit:
            os._exit(130)
