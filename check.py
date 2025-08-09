import os
import shutil
from colorama import init, Fore, Style

init(autoreset=True)

def clear_screen():
    """Clears the console screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

clear_screen()

print(f"{Fore.CYAN}========================================={Style.RESET_ALL}")
print(f"{Fore.YELLOW}  CHECK EXECUTABLES IN PATH{Style.RESET_ALL}")
print(f"{Fore.CYAN}========================================={Style.RESET_ALL}")
print("")

executables = ["flac", "rsgain"]

found_count = 0
not_found_count = 0
results = {}

for executable in executables:
    print(f"   Checking: {executable}...")

    if shutil.which(executable):
        print(f"   {Fore.GREEN}Found: '{executable}' is in the PATH.{Style.RESET_ALL}")
        found_count += 1
        results[executable] = True
    else:
        print(f"   {Fore.RED}Not found: '{executable}' is NOT in the PATH.{Style.RESET_ALL}")
        not_found_count += 1
        results[executable] = False
    print("")

