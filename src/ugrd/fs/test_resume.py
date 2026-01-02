__version__ = "2.0.0"

from zenlib.util import contains


@contains("test_resume")
def resume_tests(self):
    return """
        echo "Begin resume testing."
        if [ "$(</sys/power/resume)" != "0:0" ] ; then
            echo reboot > /sys/power/disk
            echo 1 > /sys/power/pm_debug_messages

            echo "Activating hibernation swap device..."
            swapon /dev/$(. "/sys/dev/block/$(read blk </sys/power/resume && echo $blk)/uevent" && echo $DEVNAME)

            echo "Triggering test hibernation..."
            echo disk > /sys/power/state || (echo "Suspend to disk failed!" ; echo c > /proc/sysrq-trigger)

            # Assume at this point system has hibernated then resumed again
            echo "Resume test completed without error."
        else
            echo "No resume device found! Resume test not possible!"
            echo c > /proc/sysrq-trigger
        fi
    """
