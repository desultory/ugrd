__version__ = "2.0.0"

from zenlib.util import contains

@contains("test_resume")
def resume_tests(self):
    return """
        echo "Begin resume testing."
        if [ "$(</sys/power/resume)" != "0:0" ] ; then
            echo reboot > /sys/power/disk
            echo 1 > /sys/power/pm_debug_messages

            local SWAPDEV=/dev/$(source "/sys/dev/block/$(</sys/power/resume)/uevent" && echo $DEVNAME)
            echo "Activating swap device ${SWAPDEV}..."
            swapon ${SWAPDEV}

            echo "Triggering test hibernation..."
            echo disk > /sys/power/state || (echo "Suspend to disk failed!" ; echo c > /proc/sysrq-trigger)

            # Assume at this point system has hibernated then resumed again
            echo "Resume test completed without error."
        else
            echo "No resume device found! Resume test not possible!"
            echo c > /proc/sysrq-trigger
        fi
    """
