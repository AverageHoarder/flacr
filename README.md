# flacr

## A multithreaded python script to recursively recompress or verify flac files and calculate replay gain tags

I wrote this because my music converter was out of date and updating the flac encoder was paywalled.<br>
Initially this script only used the [flac cli](https://xiph.org/flac/documentation_tools_flac.html) to recompress all .flac files in all subdirectories with the highest compression, verify their integrity and set a fixed padding.<br>
When recompressing, temporary files are created and the original files are only overwritten if no decoding errors occurred.

Then I also included [rsgain](https://github.com/complexlogic/rsgain) to calculate and write replay gain tags to all music files (not only flac files) in all subdirectories.<br>
To speed things up I added multithreading support for recompression and replay gain calculation.

Finally when I was happy with the performance and pondered making this available to others, I added a progress bar, a separate test mode and logging as I suspect that most people don't like watching a blank command line for minutes while the script does its thing.<br>

Flac version 1.5.0 added multi-threaded encoding support. I've added -j and -S to utilize this new feature. In these modes, instead of encoding multiple flac files concurrently, one flac file at a time is encoded with the specified number (via -m) of threads.

**What can this script do?**
  * recursively scan for .flac files in a given directory
  * scan for .flac files in a single given directory
  * recompress all .flac files with max compression, a fixed padding of 4KB and verification via flac CLI
  * test all .flac files for decoding errors via flac CLI
  * calculate and save replay gain tags for all music files recursively via rsgain
  * display a progress bar while scanning directories and recompressing/testing
  * log errors while recompressing/testing to console or to file

## How to install flacr

### Prerequisites

**Required:**
1. [python](https://www.python.org/downloads/) must be installed (tested with python 3.12.3)
2. [flac](https://xiph.org/flac/download.html) must be on PATH

**Optional:**
1. when using -r to calculate replay gain tags, [rsgain](https://github.com/complexlogic/rsgain) must be on PATH
2. when using -p to show progress bars, [tqdm](https://github.com/tqdm/tqdm) must be installed, I used `pip3 install tqdm`

If flac or rsgain are not on PATH, the script will complain and (if on Windows) open the environment variables settings with instructions on how to add them to PATH.

### Downloading the script

You can either download/clone the entire repository and extract "flacr.py" or you can copy the raw contents of flacr.py, paste them into a .py file and save it that way.<br>
If you want to be able to call it from anywhere on your system (which is more convenient than supplying a path via -d), you can add it to your PATH.

## Usage

### Output from -h:

```
usage: flacr.py [-h] [-d [DIRECTORY]] [-j] [-l] [-m [MULTI_THREADED]] [-p] [-r] [-s] [-t] [-Q] [-S]

Scan for .flac files in subdirectories, recompress them and optionally calculate replay gain tags.

options:
  -h, --help            show this help message and exit
  -d [DIRECTORY], --directory [DIRECTORY]
                        The directory that will be recursively scanned for .lrc and .txt files.
  -j                    flac >=1.5.0: Encode 1 file at a time with multi-threading (threadcount
                        specified via -m) instead of encoding multiple files concurrently.
  -l, --log             Log errors during recompression or testing to flacr.log.
  -m [MULTI_THREADED], --multi_threaded [MULTI_THREADED]
                        The number of threads used during conversion and replay gain calculation,
                        default: 1.
  -p, --progress        Show progress bars during scanning/recompression/testing. Useful for huge
                        directories. Requires tqdm, use "pip3 install tqdm" to install it.
  -r, --rsgain          Calculate replay gain values with rsgain and save them in the audio file
                        tags.
  -s, --single_folder   Only scan the current folder for flac files to recompress, no
                        subdirectories.
  -t, --test            Skip recompression and only log decoding errors to console or log when used
                        with -l.
  -Q, --quick           Equal to using -m with the max available threadcount, -r to calculate
                        replay gain values and -p to display a progress bar.
  -S, --sequential      Equal to using -m 4 -j to encode 1 file at a time with 4 threads, -r to
                        calculate replay gain values and -p to display a progress bar.
```

### More elaborate explanations in order of importance:

**When called without -t (overwrites music files)**  
**Recompression mode:**  
Uses flac.exe to recompress all .flac files, creates temporary files in the same folder by appending ".tmp" to the filename and only replaces the original files if no errors occurred during decoding. If errors occurred, they are logged and the temporary file is deleted. In that case the original file remains untouched. If a file is locked by another process (which prevents the replacement), the temporary file is kept and an error is logged because the original file might be deleted by the system as soon as the other process releases the lock.
This mode uses the highest level of compression (8), verifies the written files via checksum and also adds a padding of 4096 bytes.
flac command used:<br>
`flac --best --verify --padding=4096 --silent`<br>
If a flac version >=1.5.0 is used with the -j or -S flag to use multi-threading, the command is appended with `--threads=#`.

**-m, --multi-threaded INT (optional, default=1, min=1, max=thread count of the CPU)**  
Specify the number of threads which will be used during recompression, verification and replay gain calculation.<br>
Can drastically increase performance depending on the kind of storage the music resides on.<br>
For SSDs I recommend using as many threads as your CPU has.<br>
For HDDs, I would not go above 5-8 threads as that may decrease performance by increasing seek times.<br>
When in doubt, try and compare performance.<br>
Notice that rsgain will always be called with at least 2 threads (even if called with -m 1) because of a Windows cli limitation that decreases the performance of rsgain if it is called with only 1 thread.<br>

**-j (optional, uses multi-threaded sequential encoding, only available in flac v1.5.0 and higher)**  
Using the -j or -S flag allows to switch the recompression mode to multi-threaded flac encoding instead of encoding multiple flac files with 1 thread each concurrently. This has advantages if fragmentation is an issue and also when using HDDs as it reduces seeking. It also outperforms the concurrent mode if only one large file is to be recompressed. For many files at once it's generally far slower tho.<br>
The number of threads used is set via -m, however using a value higher than 4 decreased the encoding speed in my tests.

**-d, --directory PATH (optional, default=".")**  
When run without -d, the script will be called in the folder it was executed from.<br>
If -d is supplied, it must be followed by a valid path to a directory, which will be scanned for .flac files.

**-t, --test (optional, skips recompression, only reads music files)**  
Test Mode, all found .flac files are decoded via flac CLI with as many threads as specified via -m and errors are logged.<br>
flac command used:<br>
`flac -t --silent`

**-r, --rsgain (optional, writes to tags of music files)**  
Calls rsgain in easy mode in the root directory with as many threads as specified via -m. Rsgain then recursively calculates and saves replay gain tags to all music files in all subdirectories. Consult the [Easy Mode](https://github.com/complexlogic/rsgain?tab=readme-ov-file#easy-mode) documentation to learn what it does.<br>
rsgain command used:<br>
`rsgain easy`

**-l, --log**  
Log errors during recompression or testing to flacr.log.

**-p, --progress (optional)**  
Show progress bars during scanning, testing and recompression. Useful for huge directories.

**-Q, --quick (optional)**  
Alias for -r -p and -m with all available threads to quickly recompress and calculate replay gain tags.

**-S, --sequential (optional)**  
Alias for -r -p and -m with 4 threads to recompress sequentially and calculate replay gain tags.

## Common examples

### Case 1: test flac files for errors:
* log errors to console, 4 threads<br>
`flacr.py -t -m 4`

* log to file instead<br>
`flacr.py -tl -m 4"`
  
* with progress bar<br>
`flacr.py -tlp -m 4`

* with directory<br>
`flacr.py -tlp -m 4 -d "D:\Test"`

### Case 2: recompress flac files, no replay gain:
* log errors to console, 4 threads<br>
`flacr.py -m 4`
  
* log to file instead<br>
`flacr.py -l -m 4` 

* with progress bar<br>
`flacr.py -lp -m 4`

* with directory<br>
`flacr.py -lp -m 4 -d "D:\Test"`

### Case 3: recompress flac files, calculate replay gain:
* use all available threads and display progress bars<br>
`flacr.py -Q`

* use 4 threads to encode one file at a time and display progress bars<br>
`flacr.py -S`

* log errors to console, 4 threads<br>
`flacr.py -r -m 4`

* log to file instead<br>
`flacr.py -rl -m 4`
  
* with progress bar<br>
`flacr.py -rlp -m 4`

* with directory<br>
`flacr.py -rlp -m 4 -d "D:\Test"`

## How to tweak behavior

If you want to use different encoding settings, search for this comment and edit the arguments that are passed to flac in the line below it:
`    # Define the re-encoding command`

If you want to calculate replay gain in a different way, search for this comment and edit the arguments that are passed to rsgain in the line below it:
`    # Define the replay gain calculation command`