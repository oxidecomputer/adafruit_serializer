# Slightly less janky script to auto-generate a new random serial number from
# the specified alphabet below, prefix it with "FT"
#
# Depends on having ftdi_eeprom executable in your path (apt install
# ftdi-eeprom) and ptouch-print (manually built following these instructions:
# https://github.com/HenrikBengtsson/brother-ptouch-label-printer-on-linux)
import random
import subprocess
import argparse
import filecmp
import time

parser = argparse.ArgumentParser(
                    prog='adafruit_serializer',
                    description="Adafruit dongle's don't come with proper serial numbers programmed in the EEPROMs by default, this fixes it by generating a random serial number, building an EEPROM image with that serial number, flashing the EEPROM, and verifying that the EEPROM was flashed correctly by reading it back and comparing the binary files. By default, this script also prints a label with the new serial number on it using ptouch-print. You can disable this behavior with the --no-label argument.")
parser.add_argument('--sn-only',
                    dest='sn_only',
                    action='store_true',
                    default=False,
                    help='Generate a random serial number but do not flash the EEPROM.')
parser.add_argument('--no-label', dest='no_label',
                    action='store_true',
                    default=False,
                    help='Do not print a label after flashing.')
parser.add_argument('--serial-number',
                    dest='serial_number',
                    help='Specify a serial number instead of generating a random serial number')              
parser.add_argument('--verify-only',
                    dest='verify_only',
                    action='store_true',
                    default=False,
                    help='Read and verify the EEPROM image only. Do not flash.')

# TODO: Maybe Implement an --erase argument as a wrapper for ftdi_eeprom
# --erase-eeprom. Implementing this safely will require also allowing users to
# specify a device description string with the vendor_id, product_id, and serial
# number to disambiguate devices when users have multiple FT232 dongles plugged
# in to their system
#
# We could make this a little more generic by implementing a --target argument
# where users can pick the serial number they want to target and re-flash, or
# erase, for targets that have valid EEPROM images. This would be useful in
# cases where we need to reuse a dongle by giving it a serial number that's
# already hard-coded in facade somehow.

args = parser.parse_args()

# Our alphabet prohibits confusing characters
alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
sn = ""

# If the user passed the --serial-number argument, use the provided serial number
if args.serial_number:
    # TODO: Test to make sure the serial number is eight characters long and
    # doesn't contain prohibited characters
    sn = args.serial_number
    print("Using serial number: "f"{sn}")

# Otherwise, generate a serial number
# Serial numbers are the letters "FT" followed by six characters from the
# alphabet defined above.
else:
    for i in range(0, 6):
        sn += random.choice(alphabet)
    sn = "FT"+sn
    print("Generated serial number: "f"{sn}")

# Generate the EEPROM write configuration file
with open("write.cfg", "w") as outfile:
    outfile.write(f'''\
filename="eeprom-write.bin"
vendor_id="0x0403"
product_id="0x6014"
manufacturer="Adafruit"
product="FT232H"
serial="{sn}"
use_serial=true
high_current=false
max_power=100
remote_wakeup=false
self_powered=false
cbush0=TRISTATE
cbush1=TRISTATE
cbush2=TRISTATE
cbush3=TRISTATE
cbush4=TRISTATE
cbush5=TRISTATE
cbush6=TRISTATE
cbush7=TRISTATE
cbush8=DRIVE1
cbush9=DRIVE_0
''')
    
# Generate the EEPROM read configuration file
# TODO: Right now, the read configuration file just contains the filename for
# the binary we read, the vendor_id, and the product_id. This is mostly an
# attempt to make sure ftdi_eeprom tries to read the correct device. I don't
# know if it's strictly necessary to specify these things.
with open("read.cfg", "w") as outfile:
    outfile.write(f'''\
filename="eeprom-read.bin"
vendor_id="0x0403"
product_id="0x6014"
''')

if not args.sn_only:

    # Build the EEPROM image
    print("Building EEPROM image")
    subprocess.run("ftdi_eeprom --build-eeprom write.cfg", shell=True, check=True)

    # Write the EEPROM image (unless the user passed the --verify-only argument)
    if not args.verify_only:
        print("Flashing EEPROM image")
        subprocess.run("ftdi_eeprom --flash-eeprom write.cfg" , shell=True, check=True)

        # Wait for a non-zero amount of time between flashing the EEPROM and
        # attempting to read the EEPROM. The last thing --flash-eeprom does is
        # perform a USB device reset, and if you try to read the EEPROM before
        # the reset completes, you're going to have a bad time
        print("Waiting 1 second for USB device reset")
        time.sleep(1)

    # Read the EEPROM image
    print("Reading EEPROM image")
    subprocess.run("ftdi_eeprom --read-eeprom read.cfg", shell=True, check=True)

    # Verify the EEPROM image
    # Currently, we just compare the two binary files exactly.
    print("Verifying EEPROM image")
    if filecmp.cmp("eeprom-write.bin", "eeprom-read.bin", shallow=False):
        print("Verification passed!")
    else:
        print("ERROR: Verification failed!")
        # TODO: If the EEPROM images don't match, print the EEPROM contents from
        # write.cfg and read.cfg so users can compare them
        #
        # TODO: Currently, verification will fail if you specify --verify-only
        # without also specifying a serial number using --force-sn. This is
        # because the verification check only passes if the EEPROM binary files
        # are exactly the same, and we generate the "good" binary file each time
        # the script runs.
        # 
        # In the future, what we'd really like to use the --verify-only check
        # for is to test whether a random dongle on the bench has been flashed
        # with a valid EEPROM image, and if so, get it's serial number without
        # having to go mucking about in USB space.
        #
        # To do this, we need to update the filecmp check to actually parse
        # eeprom-read.bin and compare it to the image we build, which can be a
        # representative image with an arbitrary serial number. When parsing the
        # image we read back, we just test to make sure is a valid serial number
        # (i.e., it's six characters long and only uses characters from the
        # permitted alphabet)

# If the user passed the --label argument, print a label
if not args.no_label:
    print("Printing label")
    subprocess.run(f"ptouch-print --fontsize 20 --text \"{sn} \"", shell=True, check=True)