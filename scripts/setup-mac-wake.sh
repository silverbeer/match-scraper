#!/bin/bash
# Setup Mac Mini to wake daily for cronjob execution
# This ensures the Mac is awake when k3s cronjobs are scheduled to run

set -e

echo "🌅 Setting up Mac wake schedule for match-scraper cronjobs"
echo ""

# Clear any existing scheduled wakeups
echo "Clearing existing wake schedules..."
sudo pmset repeat cancel

# Schedule daily wake at 6:55 AM EST
# This wakes the Mac 5 minutes before the cronjobs run at 7:00 AM EST
echo "Scheduling daily wake at 6:55 AM EST..."
sudo pmset repeat wakeorpoweron MTWRFSU 06:55:00

echo ""
echo "✅ Mac will now wake daily at 6:55 AM EST"
echo ""
echo "Cronjobs will run at:"
echo "  - 7:00 AM EST (Homegrown U14)"
echo "  - 7:30 AM EST (Academy U14)"
echo ""
echo "Current schedule:"
pmset -g sched
echo ""
echo "To verify: pmset -g sched"
echo "To cancel: sudo pmset repeat cancel"
