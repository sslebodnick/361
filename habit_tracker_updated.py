import json
import os
from datetime import date
import time
import requests

# ASCII art title
TITLE = '''
=======================
    HABIT TRACKER
=======================
"We are what we repeatedly do. Excellence, then, is not an act,
but a habit." - Aristotle

NOTE: Track your habits in under 2 minutes a day!
'''

DATA_FILE = "habits.json"
TIMER_SERVICE_URL = "http://localhost:3001"  # Timer microservice endpoint
REMINDER_SERVICE_URL = "http://localhost:3000"  # Reminder microservice endpoint
FORMATTER_SERVICE_URL = "http://localhost:3002"  # Formatter microservice endpoint

COMMANDS = '''
COMMANDS:
Type 'new' to add a new habit to track
Type 'mark' to mark a habit as completed for today
Type 'timed' to start a timer, do your habit, then mark it complete with time tracked
Type 'remind' to set up reminders for your habits
Type 'view' to see all your habits and progress
Type 'do' to quickly complete a reminded habit (when reminders show above)
Type 'edit' to rename an existing habit
Type 'remove' to delete an existing habit
Type 'about' to learn why this program was created
Type 'q' or 'quit' to exit the program
'''

# Map commands to functions (keeps `main()` short so it's under 10 lines)
COMMAND_MAP = {
    'n': 'add_habit', 'new': 'add_habit',
    'm': 'mark_habit', 'mark': 'mark_habit',
    'v': 'view_habits', 'view': 'view_habits',
    'e': 'edit_habit', 'edit': 'edit_habit',
    'r': 'remove_habit', 'remove': 'remove_habit',
    'about': 'about'
}

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        data = json.load(f)
        # Migrate old format to new format if needed
        for habit, entries in data.items():
            if entries and isinstance(entries[0], str):
                # Old format: just dates. Convert to new format
                data[habit] = [{'date': d, 'duration': None} for d in entries]
        return data

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def print_with_delay(message, delay=0.01):
    for char in message:
        print(char, end='', flush=True)
        time.sleep(delay)
    print()

def pause():
    input("\nPress Enter to continue...")

# Timer microservice functions
def check_timer_service():
    """Check if timer microservice is running"""
    try:
        response = requests.get(f'{TIMER_SERVICE_URL}/timers', timeout=2)
        return response.status_code == 200
    except:
        return False

def start_timer(label):
    """Start a timer via microservice"""
    try:
        response = requests.post(f'{TIMER_SERVICE_URL}/timers/start', 
                                json={'label': label}, timeout=2)
        result = response.json()
        if result.get('success'):
            return result['timer']['id']
    except:
        pass
    return None

def stop_timer(timer_id):
    """Stop a timer and get elapsed time"""
    try:
        response = requests.post(f'{TIMER_SERVICE_URL}/timers/{timer_id}/stop', timeout=2)
        result = response.json()
        if result.get('success'):
            return result['timer']['elapsedTime']
    except:
        pass
    return None

def format_duration(duration_data):
    """Format duration data for display"""
    if not duration_data:
        return "N/A"
    if isinstance(duration_data, dict):
        return duration_data.get('formatted', 'N/A')
    return str(duration_data)

# Reminder microservice functions
def check_reminder_service():
    """Check if reminder microservice is running"""
    try:
        response = requests.get(f'{REMINDER_SERVICE_URL}/reminders', timeout=2)
        return response.status_code == 200
    except:
        return False

def create_timed_reminder(message, seconds):
    """Create a timed reminder"""
    try:
        response = requests.post(f'{REMINDER_SERVICE_URL}/reminders',
                                json={'message': message, 'seconds': seconds}, timeout=2)
        result = response.json()
        return result.get('success', False)
    except:
        return False

def create_daily_reminder(habit_name, hours_from_now):
    """Create a recurring daily reminder for a habit"""
    try:
        # Create BOTH a one-time reminder for the first notification
        # AND a recurring reminder that starts in 24 hours
        seconds_per_day = 24 * 60 * 60
        initial_seconds = hours_from_now * 3600
        message = f"⏰ Time to do your habit: {habit_name}"
        
        # First: Create one-time reminder for initial notification
        first_response = requests.post(f'{REMINDER_SERVICE_URL}/reminders',
                                      json={
                                          'message': message,
                                          'seconds': initial_seconds
                                      }, timeout=2)
        
        # Second: Create recurring daily reminder starting 24 hours from now
        # This ensures daily reminders continue after the first one
        recurring_response = requests.post(f'{REMINDER_SERVICE_URL}/reminders/recurring',
                                json={
                                    'message': message,
                                    'duration_seconds': seconds_per_day,  # 24 hours
                                    'recurrences': 365,  # One year of daily reminders
                                    'interval': 'daily'
                                }, timeout=2)
        
        # Success if at least one worked
        first_ok = first_response.json().get('success', False) if first_response.status_code == 201 else False
        recurring_ok = recurring_response.json().get('success', False) if recurring_response.status_code == 201 else False
        
        return first_ok or recurring_ok
    except:
        return False

def get_all_reminders():
    """Get all active reminders"""
    try:
        response = requests.get(f'{REMINDER_SERVICE_URL}/reminders', timeout=2)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return []

def delete_reminder(reminder_id):
    """Delete a specific reminder by ID"""
    try:
        response = requests.delete(f'{REMINDER_SERVICE_URL}/reminders/{reminder_id}', timeout=2)
        result = response.json()
        return result.get('success', False)
    except:
        return False

def delete_all_fired_reminders():
    """Delete all fired reminders"""
    try:
        response = requests.delete(f'{REMINDER_SERVICE_URL}/reminders/fired/all', timeout=2)
        result = response.json()
        return result.get('success', False), result.get('deletedCount', 0)
    except:
        return False, 0

# Formatter microservice functions
def check_formatter_service():
    """Check if formatter microservice is running"""
    try:
        response = requests.get(f'{FORMATTER_SERVICE_URL}/health', timeout=2)
        return response.status_code == 200
    except:
        return False

def format_text(text):
    """
    Format text using the microservice.
    Returns formatted text, or original if service unavailable.
    Provides automatic cleanup of:
    - Leading/trailing spaces
    - Multiple spaces between words
    - Capitalization
    - Ending punctuation
    """
    if not text or not text.strip():
        return text
    
    try:
        response = requests.post(f'{FORMATTER_SERVICE_URL}/format',
                                json={'text': text}, timeout=2)
        result = response.json()
        if result.get('success'):
            return result['formatted']
    except:
        pass
    
    # Fallback: return original text if service unavailable
    return text

def get_fired_habit_reminders():
    """Get reminders that have fired and contain specific tracked habit names"""
    try:
        reminders = get_all_reminders()
        if not reminders:
            return []
        
        # Get user's actual habits
        data = load_data()
        if not data:
            return []
        
        habit_names = list(data.keys())
        
        # Filter for fired reminders that mention specific habits
        fired_reminders = []
        for reminder in reminders:
            if reminder.get('fired', False):
                message = reminder.get('message', '')
                
                # Check if message contains any actual tracked habit name
                contains_habit = False
                for habit in habit_names:
                    if habit.lower() in message.lower():
                        contains_habit = True
                        break
                
                # Only include if it mentions a specific tracked habit
                if contains_habit:
                    fired_reminders.append(message)
        
        return fired_reminders
    except:
        return []

def extract_habits_from_reminder(message):
    """Extract habit names from reminder message"""
    # Try to extract habits after ':' in messages like "Time to do your habit: Meditation"
    if ':' in message:
        parts = message.split(':', 1)
        if len(parts) == 2:
            habit_part = parts[1].strip()
            # Could be single habit or comma-separated
            if ',' in habit_part:
                return [h.strip() for h in habit_part.split(',')]
            else:
                return [habit_part]
    return []

def list_habits(data):
    print("\nYour habits:")
    for i, h in enumerate(data.keys(), 1):
        print(f"{i}. {h}")

def resolve_choice(data, choice):
    if not choice:
        return None
    if choice.isdigit():
        idx = int(choice) - 1
        return list(data.keys())[idx] if 0 <= idx < len(data) else None
    return choice

def select_habit(prompt):
    data = load_data()
    if not data:
        print_with_delay("\nNo habits available.")
        pause()
        return None, None
    list_habits(data)
    choice = input(prompt)
    name = resolve_choice(data, choice)
    return data, name

def add_habit():
    clear_screen(); print_with_delay("\nADDING NEW HABIT"); print_with_delay("----------------")
    name = input("\nWhat habit would you like to track? (or press Enter to cancel): ")
    if not name:
        print_with_delay("\nCancelled adding new habit.")
        pause(); return
    
    # Format the habit name for consistency
    formatted_name = format_text(name)
    if formatted_name != name and formatted_name.strip():
        print_with_delay(f"\n✨ Formatted as: '{formatted_name}'")
    
    data = load_data()
    if formatted_name in data:
        print_with_delay("\nThis habit is already being tracked!")
    else:
        data[formatted_name] = []
        save_data(data); print_with_delay(f"\nGreat! I'll help you track '{formatted_name}'.")
        print_with_delay("\nTips:")
        print_with_delay("  • Use 'timed' to track how long you spend on this habit")
        print_with_delay("  • Use 'remind' to set up daily reminders for this habit")
    pause()

def mark_habit():
    clear_screen(); print_with_delay("\nMARK HABIT COMPLETE"); print_with_delay("------------------")
    data, name = select_habit("\nWhich habit did you complete? (enter name or number, or press Enter to cancel): ")
    if not name:
        print_with_delay("\nCancelled marking habit.")
        return
    if name not in data:
        print_with_delay("\nHabit not found. Please try again.")
        pause(); return
    today = str(date.today())
    # Check if already completed today
    if any(entry.get('date') == today for entry in data[name] if isinstance(entry, dict)):
        print_with_delay(f"\nYou've already marked '{name}' as complete today. Great job!")
    else:
        data[name].append({'date': today, 'duration': None})
        save_data(data)
        print_with_delay(f"\nAwesome! '{name}' marked as completed for today!")
        print_with_delay("\nTip: Use 'timed' command next time to track how long it takes!")
    pause()

def view_habits():
    clear_screen(); data = load_data(); print_with_delay("\nYOUR HABITS & PROGRESS")
    print_with_delay("--------------------")
    if not data:
        print_with_delay("\nNo habits found. Try adding one!")
        pause(); return
    today = str(date.today())
    
    incomplete_habits = []
    
    for habit, entries in data.items():
        # Check if completed today
        completed_today = any(entry.get('date') == today for entry in entries if isinstance(entry, dict))
        status = "✓" if completed_today else "○"
        
        if not completed_today:
            incomplete_habits.append(habit)
        
        print(f"\n{status} {habit}")
        print(f"   Total completions: {len(entries)}")
        
        if entries:
            # Get last completion
            last_entry = entries[-1]
            if isinstance(last_entry, dict):
                print(f"   Last completed: {last_entry['date']}", end="")
                if last_entry.get('duration'):
                    duration = format_duration(last_entry['duration'])
                    print(f" ({duration})")
                else:
                    print()
            
            # Calculate average time if we have timed entries
            timed_entries = [e for e in entries if isinstance(e, dict) and e.get('duration')]
            if timed_entries:
                total_seconds = sum(e['duration'].get('totalSeconds', 0) for e in timed_entries)
                avg_seconds = total_seconds // len(timed_entries)
                avg_hours = avg_seconds // 3600
                avg_minutes = (avg_seconds % 3600) // 60
                avg_secs = avg_seconds % 60
                avg_formatted = f"{avg_hours:02d}:{avg_minutes:02d}:{avg_secs:02d}"
                print(f"   Average time: {avg_formatted} ({len(timed_entries)} timed sessions)")
    
    # Offer to set reminders for incomplete habits
    if incomplete_habits and check_reminder_service():
        print_with_delay(f"\n\n💡 You have {len(incomplete_habits)} habit(s) not completed today.")
        choice = input("\nWould you like to set a reminder to do them later? (y/N): ").lower().strip()
        if choice in ('y', 'yes'):
            print_with_delay("\nChoose time unit:")
            print_with_delay("1. Seconds")
            print_with_delay("2. Minutes")
            print_with_delay("3. Hours")
            
            unit_choice = input("\nSelect unit (1-3): ").strip()
            
            try:
                if unit_choice == '1':
                    # Seconds
                    seconds_input = int(input("\nRemind me in how many seconds? (30-3600): "))
                    if 30 <= seconds_input <= 3600:
                        seconds = seconds_input
                        time_str = f"{seconds} second(s)"
                    else:
                        print_with_delay("\n⚠️  Please enter 30-3600 seconds.")
                        pause()
                        return
                        
                elif unit_choice == '2':
                    # Minutes
                    minutes = int(input("\nRemind me in how many minutes? (1-1440): "))
                    if 1 <= minutes <= 1440:
                        seconds = minutes * 60
                        time_str = f"{minutes} minute(s)"
                    else:
                        print_with_delay("\n⚠️  Please enter 1-1440 minutes.")
                        pause()
                        return
                        
                elif unit_choice == '3':
                    # Hours
                    hours = int(input("\nRemind me in how many hours? (1-24): "))
                    if 1 <= hours <= 24:
                        seconds = hours * 3600
                        time_str = f"{hours} hour(s)"
                    else:
                        print_with_delay("\n⚠️  Please enter 1-24 hours.")
                        pause()
                        return
                else:
                    print_with_delay("\n⚠️  Invalid choice.")
                    pause()
                    return
                
                habits_list = ", ".join(incomplete_habits)
                message = f"⏰ Don't forget your habits: {habits_list}"
                if create_timed_reminder(message, seconds):
                    print_with_delay(f"\n✅ Reminder set for {time_str} from now!")
                else:
                    print_with_delay("\n❌ Failed to create reminder.")
            except ValueError:
                print_with_delay("\n⚠️  Invalid input.")
    
    pause()

def timed_habit():
    """Start a timer, do a habit, then mark it complete with time tracked"""
    clear_screen()
    print_with_delay("\nTIMED HABIT TRACKING")
    print_with_delay("--------------------")
    print_with_delay("\nThis feature lets you time how long you spend on a habit.")
    
    # Check if timer service is available
    if not check_timer_service():
        print_with_delay("\n⚠️  Timer microservice is not running!")
        print_with_delay("\nTo use timed tracking, please start the timer service:")
        print_with_delay("  1. Open a new terminal")
        print_with_delay("  2. Navigate to: CS361-Group-41-Timer-Big-Pool-Microservice")
        print_with_delay("  3. Run: node server.js")
        print_with_delay("\nFor now, you can use the regular 'mark' command instead.")
        pause()
        return
    
    data, name = select_habit("\nWhich habit are you about to do? (enter name or number, or press Enter to cancel): ")
    if not name:
        print_with_delay("\nCancelled timed tracking.")
        return
    if name not in data:
        print_with_delay("\nHabit not found. Please try again.")
        pause()
        return
    
    # Check if already completed today
    today = str(date.today())
    if any(entry.get('date') == today for entry in data[name] if isinstance(entry, dict)):
        print_with_delay(f"\n⚠️  You've already marked '{name}' as complete today.")
        choice = input("\nDo you want to track another session anyway? (y/N): ").lower().strip()
        if choice not in ('y', 'yes'):
            print_with_delay("\nCancelled timed tracking.")
            pause()
            return
    
    # Start the timer
    print_with_delay(f"\n🎬 Starting timer for '{name}'...")
    timer_id = start_timer(name)
    
    if not timer_id:
        print_with_delay("\n❌ Failed to start timer. Please try again.")
        pause()
        return
    
    print_with_delay(f"\n✅ Timer started! (ID: {timer_id})")
    print_with_delay(f"\nNow go do your habit: '{name}'")
    print_with_delay("\nWhen you're done, press Enter to stop the timer...")
    
    input()
    
    # Stop the timer
    print_with_delay("\n⏹️  Stopping timer...")
    elapsed = stop_timer(timer_id)
    
    if not elapsed:
        print_with_delay("\n❌ Failed to stop timer. Marking habit without time data.")
        data[name].append({'date': today, 'duration': None})
        save_data(data)
        pause()
        return
    
    # Save the completion with time data
    data[name].append({'date': today, 'duration': elapsed})
    save_data(data)
    
    print_with_delay(f"\n🎉 Awesome! '{name}' completed!")
    print_with_delay(f"\n⏱️  Time spent: {elapsed['formatted']}")
    print_with_delay(f"   ({elapsed['totalSeconds']} seconds)")
    
    # Show some encouragement based on time
    if elapsed['totalSeconds'] >= 300:  # 5 minutes or more
        print_with_delay("\n💪 Great dedication! That's some quality time invested!")
    elif elapsed['totalSeconds'] >= 60:
        print_with_delay("\n👍 Nice work! Every minute counts!")
    else:
        print_with_delay("\n⚡ Quick and efficient! Consistency is key!")
    
    pause()

def edit_habit():
    clear_screen(); print_with_delay("\nRENAME HABIT"); print_with_delay("-----------")
    data, old = select_habit("\nWhich habit would you like to rename? (enter name or number, or press Enter to cancel): ")
    if not old:
        print_with_delay("\nCancelled renaming."); return
    if old not in data:
        print_with_delay("\nHabit not found. Please try again."); pause(); return
    new = input(f"\nEnter the new name for '{old}' (or press Enter to cancel): ")
    if not new or new == old:
        print_with_delay("\nRename cancelled or unchanged."); pause(); return
    
    # Format the new habit name for consistency
    formatted_new = format_text(new)
    if formatted_new != new and formatted_new.strip():
        print_with_delay(f"\n✨ Formatted as: '{formatted_new}'")
    
    if formatted_new in data:
        print_with_delay(f"\nA habit named '{formatted_new}' already exists. Choose a different name."); pause(); return
    data[formatted_new] = data.pop(old); save_data(data); print_with_delay(f"\nRenamed '{old}' to '{formatted_new}'.")
    pause()

def remove_habit():
    clear_screen(); print_with_delay("\nREMOVE HABIT"); print_with_delay("-----------")
    data, name = select_habit("\nWhich habit would you like to remove? (enter name or number, or press Enter to cancel): ")
    if not name:
        print_with_delay("\nCancelled removal."); return
    if name not in data:
        print_with_delay("\nHabit not found. Please try again."); pause(); return
    if input(f"\nAre you sure you want to remove '{name}'? (y/N): ").lower().strip() not in ('y','yes'):
        print_with_delay("\nRemoval cancelled."); pause(); return
    if input("\nThis is permanent. Type DELETE to confirm removal (or press Enter to cancel): ") != 'DELETE':
        print_with_delay("\nRemoval cancelled."); pause(); return
    data.pop(name); save_data(data); print_with_delay(f"\nHabit '{name}' has been removed permanently.")
    pause()

def setup_reminders():
    """Set up reminders for habits"""
    clear_screen()
    print_with_delay("\nREMINDER SETUP")
    print_with_delay("--------------")
    print_with_delay("\nSet up reminders to help you remember your habits!")
    
    # Check if reminder service is available
    if not check_reminder_service():
        print_with_delay("\n⚠️  Reminder microservice is not running!")
        print_with_delay("\nTo use reminders, please start the reminder service:")
        print_with_delay("  1. Open a new terminal")
        print_with_delay("  2. Navigate to: CS361-Group-41-Reminder-Microservice")
        print_with_delay("  3. Run: node server.js")
        pause()
        return
    
    print_with_delay("\nReminder Options:")
    print_with_delay("1. Set a one-time reminder for a specific habit")
    print_with_delay("2. Set a daily reminder for a specific habit")
    print_with_delay("3. View all active reminders")
    print_with_delay("4. Delete/manage reminders")
    print_with_delay("5. Cancel")
    
    choice = input("\nSelect an option (1-5): ").strip()
    
    if choice == '1':
        # One-time reminder for a specific habit
        data = load_data()
        if not data:
            print_with_delay("\nNo habits available to set reminders for.")
            print_with_delay("Create a habit first using 'new' command.")
            pause()
            return
        
        clear_screen()
        print_with_delay("\nONE-TIME HABIT REMINDER")
        print_with_delay("-----------------------")
        
        # Select habit
        data, name = select_habit("\nWhich habit would you like to be reminded of? (enter name or number, or press Enter to cancel): ")
        if not name or name not in data:
            print_with_delay("\nCancelled reminder setup.")
            pause()
            return
        
        # Choose time unit
        clear_screen()
        print_with_delay(f"\nREMINDER FOR: {name}")
        print_with_delay("-" * (14 + len(name)))
        print_with_delay("\nChoose time unit:")
        print_with_delay("1. Seconds (10-3600 seconds)")
        print_with_delay("2. Minutes (1-1440 minutes)")
        print_with_delay("3. Hours (1-24 hours)")
        
        unit_choice = input("\nSelect unit (1-3): ").strip()
        
        try:
            if unit_choice == '1':
                # Seconds
                seconds_input = int(input("\nRemind me in how many seconds? (10-3600): "))
                if seconds_input < 10 or seconds_input > 3600:
                    print_with_delay("\n⚠️  Please enter a number between 10 and 3600 seconds.")
                    pause()
                    return
                seconds = seconds_input
                time_str = f"{seconds} second(s)"
                
            elif unit_choice == '2':
                # Minutes
                minutes = int(input("\nRemind me in how many minutes? (1-1440): "))
                if minutes < 1 or minutes > 1440:
                    print_with_delay("\n⚠️  Please enter a number between 1 and 1440 minutes.")
                    pause()
                    return
                seconds = minutes * 60
                time_str = f"{minutes} minute(s)"
                
            elif unit_choice == '3':
                # Hours
                hours = int(input("\nRemind me in how many hours? (1-24): "))
                if hours < 1 or hours > 24:
                    print_with_delay("\n⚠️  Please enter a number between 1 and 24 hours.")
                    pause()
                    return
                seconds = hours * 3600
                time_str = f"{hours} hour(s)"
                
            else:
                print_with_delay("\n⚠️  Invalid choice.")
                pause()
                return
            
            # Create reminder with specific habit name
            message = f"⏰ Time to do your habit: {name}"
            
            if create_timed_reminder(message, seconds):
                print_with_delay(f"\n✅ Reminder set for '{name}'!")
                print_with_delay(f"\nYou'll be reminded in {time_str}.")
                print_with_delay("\n💡 Tip: Use 'do' command when the reminder fires to quickly complete it!")
            else:
                print_with_delay("\n❌ Failed to create reminder.")
        except ValueError:
            print_with_delay("\n⚠️  Invalid input. Please enter a number.")
        
        pause()
    
    elif choice == '2':
        # Daily habit reminder
        data, name = select_habit("\nWhich habit would you like daily reminders for? (enter name or number, or press Enter to cancel): ")
        if not name or name not in data:
            print_with_delay("\nCancelled reminder setup.")
            pause()
            return
        
        clear_screen()
        print_with_delay(f"\nDAILY REMINDER FOR: {name}")
        print_with_delay("-" * (20 + len(name)))
        
        try:
            hours = int(input("\nRemind me in how many hours from now? (1-24): "))
            if hours < 1 or hours > 24:
                print_with_delay("\n⚠️  Please enter a number between 1 and 24.")
                pause()
                return
            
            if create_daily_reminder(name, hours):
                print_with_delay(f"\n✅ Daily reminder set for '{name}'!")
                print_with_delay(f"\nYou'll be reminded in {hours} hour(s), then daily after that.")
                print_with_delay("\nNote: The reminder service must stay running for this to work.")
            else:
                print_with_delay("\n❌ Failed to create daily reminder.")
        except ValueError:
            print_with_delay("\n⚠️  Invalid input. Please enter a number.")
        
        pause()
    
    elif choice == '3':
        # View all reminders
        clear_screen()
        print_with_delay("\nACTIVE REMINDERS")
        print_with_delay("----------------")
        
        reminders = get_all_reminders()
        if not reminders:
            print_with_delay("\nNo active reminders found.")
        else:
            habit_reminders = [r for r in reminders if 'habit' in r.get('message', '').lower()]
            
            if not habit_reminders:
                print_with_delay("\nNo habit-related reminders found.")
            else:
                print_with_delay(f"\nFound {len(habit_reminders)} habit reminder(s):\n")
                for i, reminder in enumerate(habit_reminders, 1):
                    msg = reminder.get('message', 'N/A')
                    reminder_type = reminder.get('type', 'timed')
                    status = 'FIRED' if reminder.get('fired', False) else 'ACTIVE'
                    
                    print(f"{i}. [{status}] {msg}")
                    if reminder_type == 'recurring':
                        remaining = reminder.get('remaining', 0)
                        print(f"   Type: Daily Recurring ({remaining} remaining)")
                    else:
                        print(f"   Type: One-time")
                    print()
        
        pause()
    
    elif choice == '4':
        # Delete/manage reminders
        clear_screen()
        print_with_delay("\nMANAGE REMINDERS")
        print_with_delay("----------------")
        
        reminders = get_all_reminders()
        if not reminders:
            print_with_delay("\nNo reminders found.")
            pause()
            return
        
        # Filter for habit-related reminders
        habit_reminders = [r for r in reminders if 'habit' in r.get('message', '').lower()]
        
        if not habit_reminders:
            print_with_delay("\nNo habit-related reminders found.")
            pause()
            return
        
        print_with_delay(f"\nFound {len(habit_reminders)} habit reminder(s):\n")
        for i, reminder in enumerate(habit_reminders, 1):
            msg = reminder.get('message', 'N/A')
            reminder_type = reminder.get('type', 'timed')
            status = 'FIRED' if reminder.get('fired', False) else 'ACTIVE'
            reminder_id = reminder.get('id')
            
            print(f"{i}. [{status}] {msg}")
            print(f"   ID: {reminder_id}")
            if reminder_type == 'recurring':
                remaining = reminder.get('remaining', 0)
                print(f"   Type: Daily Recurring ({remaining} remaining)")
            else:
                print(f"   Type: One-time")
            print()
        
        print_with_delay("\nDelete Options:")
        print_with_delay("1. Delete a specific reminder by number")
        print_with_delay("2. Delete all fired reminders")
        print_with_delay("3. Cancel")
        
        delete_choice = input("\nSelect option (1-3): ").strip()
        
        if delete_choice == '1':
            # Delete specific reminder
            try:
                reminder_num = int(input(f"\nWhich reminder to delete? (1-{len(habit_reminders)}): "))
                if 1 <= reminder_num <= len(habit_reminders):
                    reminder_to_delete = habit_reminders[reminder_num - 1]
                    reminder_id = reminder_to_delete.get('id')
                    
                    confirm = input(f"\nDelete '{reminder_to_delete.get('message')}'? (y/N): ").lower().strip()
                    if confirm in ('y', 'yes'):
                        if delete_reminder(reminder_id):
                            print_with_delay("\n✅ Reminder deleted successfully!")
                        else:
                            print_with_delay("\n❌ Failed to delete reminder.")
                    else:
                        print_with_delay("\nDeletion cancelled.")
                else:
                    print_with_delay("\n⚠️  Invalid reminder number.")
            except ValueError:
                print_with_delay("\n⚠️  Invalid input.")
        
        elif delete_choice == '2':
            # Delete all fired reminders
            fired_count = sum(1 for r in habit_reminders if r.get('fired', False))
            if fired_count == 0:
                print_with_delay("\nNo fired reminders to delete.")
            else:
                confirm = input(f"\nDelete all {fired_count} fired reminder(s)? (y/N): ").lower().strip()
                if confirm in ('y', 'yes'):
                    success, deleted_count = delete_all_fired_reminders()
                    if success:
                        print_with_delay(f"\n✅ Deleted {deleted_count} fired reminder(s)!")
                    else:
                        print_with_delay("\n❌ Failed to delete fired reminders.")
                else:
                    print_with_delay("\nDeletion cancelled.")
        else:
            print_with_delay("\nCancelled.")
        
        pause()
    
    else:
        print_with_delay("\nCancelled reminder setup.")
        pause()

def do_reminded_habit(fired_reminders):
    """Quick action to complete a habit from fired reminders"""
    clear_screen()
    print_with_delay("\nCOMPLETE REMINDED HABIT")
    print_with_delay("----------------------")
    
    # Extract all habit names from fired reminders
    all_habits = []
    for message in fired_reminders:
        habits = extract_habits_from_reminder(message)
        all_habits.extend(habits)
    
    # Remove duplicates while preserving order
    unique_habits = []
    for h in all_habits:
        if h and h not in unique_habits:
            unique_habits.append(h)
    
    if not unique_habits:
        print_with_delay("\nCouldn't identify specific habits from reminders.")
        print_with_delay("Use 'mark' or 'timed' to complete habits manually.")
        pause()
        return
    
    # Get user's actual habits
    data = load_data()
    
    # Match reminded habits with actual habits (case-insensitive)
    matched_habits = []
    for reminded in unique_habits:
        for actual in data.keys():
            if reminded.lower() == actual.lower():
                matched_habits.append(actual)
                break
    
    if not matched_habits:
        print_with_delay(f"\nReminded habits: {', '.join(unique_habits)}")
        print_with_delay("\nNone of these match your tracked habits.")
        print_with_delay("Use 'mark' or 'timed' to complete habits manually.")
        pause()
        return
    
    print_with_delay("\nYou were reminded about:")
    for i, habit in enumerate(matched_habits, 1):
        print(f"{i}. {habit}")
    
    print_with_delay("\nHow would you like to complete it?")
    print_with_delay("1. Quick mark (no timer)")
    print_with_delay("2. Track time with timer")
    print_with_delay("3. Cancel")
    
    choice = input("\nSelect option (1-3): ").strip()
    
    if choice == '1':
        # Quick mark
        if len(matched_habits) == 1:
            habit_name = matched_habits[0]
        else:
            habit_choice = input(f"\nWhich habit? (1-{len(matched_habits)}): ").strip()
            try:
                idx = int(habit_choice) - 1
                if 0 <= idx < len(matched_habits):
                    habit_name = matched_habits[idx]
                else:
                    print_with_delay("\nInvalid choice.")
                    pause()
                    return
            except ValueError:
                print_with_delay("\nInvalid input.")
                pause()
                return
        
        today = str(date.today())
        if any(entry.get('date') == today for entry in data[habit_name] if isinstance(entry, dict)):
            print_with_delay(f"\n'{habit_name}' already completed today!")
        else:
            data[habit_name].append({'date': today, 'duration': None})
            save_data(data)
            print_with_delay(f"\n✅ '{habit_name}' marked complete!")
        
        # Offer to clear fired reminders
        cleanup_choice = input("\nClear fired reminders for this habit? (Y/n): ").lower().strip()
        if cleanup_choice != 'n':
            success, deleted_count = delete_all_fired_reminders()
            if success and deleted_count > 0:
                print_with_delay(f"🗑️  Cleared {deleted_count} fired reminder(s).")
        
        pause()
        
    elif choice == '2':
        # Use timed tracking
        if len(matched_habits) == 1:
            habit_name = matched_habits[0]
        else:
            habit_choice = input(f"\nWhich habit? (1-{len(matched_habits)}): ").strip()
            try:
                idx = int(habit_choice) - 1
                if 0 <= idx < len(matched_habits):
                    habit_name = matched_habits[idx]
                else:
                    print_with_delay("\nInvalid choice.")
                    pause()
                    return
            except ValueError:
                print_with_delay("\nInvalid input.")
                pause()
                return
        
        # Check timer service
        if not check_timer_service():
            print_with_delay("\n⚠️  Timer service not running. Marking without time...")
            today = str(date.today())
            if not any(entry.get('date') == today for entry in data[habit_name] if isinstance(entry, dict)):
                data[habit_name].append({'date': today, 'duration': None})
                save_data(data)
                print_with_delay(f"\n✅ '{habit_name}' marked complete!")
            pause()
            return
        
        # Start timer
        print_with_delay(f"\n🎬 Starting timer for '{habit_name}'...")
        timer_id = start_timer(habit_name)
        
        if not timer_id:
            print_with_delay("\n❌ Failed to start timer.")
            pause()
            return
        
        print_with_delay(f"\n✅ Timer started!")
        print_with_delay(f"\nGo do '{habit_name}' and press Enter when done...")
        input()
        
        # Stop timer
        print_with_delay("\n⏹️  Stopping timer...")
        elapsed = stop_timer(timer_id)
        
        today = str(date.today())
        if elapsed:
            data[habit_name].append({'date': today, 'duration': elapsed})
            save_data(data)
            print_with_delay(f"\n🎉 '{habit_name}' completed in {elapsed['formatted']}!")
        else:
            data[habit_name].append({'date': today, 'duration': None})
            save_data(data)
            print_with_delay(f"\n✅ '{habit_name}' marked complete!")
        
        # Offer to clear fired reminders
        cleanup_choice = input("\nClear fired reminders for this habit? (Y/n): ").lower().strip()
        if cleanup_choice != 'n':
            success, deleted_count = delete_all_fired_reminders()
            if success and deleted_count > 0:
                print_with_delay(f"🗑️  Cleared {deleted_count} fired reminder(s).")
        
        pause()
    else:
        print_with_delay("\nCancelled.")
        pause()

def about():
    clear_screen(); print_with_delay("\nABOUT THIS PROGRAM"); print_with_delay("-------------------")
    print_with_delay("\nI created this program because I wanted to develop new habits and be able to track them easily.")
    print_with_delay("Use this tool to record your daily wins and review progress over time.")
    print_with_delay("\nNow with integrated microservices:")
    print_with_delay("  ⏱️  Timer Service - Track time spent on habits")
    print_with_delay("  ⏰ Reminder Service - Never forget to do your habits")
    print_with_delay("  ✨ Formatter Service - Automatically clean up habit names")
    
    # Show microservice status
    print_with_delay("\nMicroservice Status:")
    timer_status = "✅ Running" if check_timer_service() else "❌ Not running"
    reminder_status = "✅ Running" if check_reminder_service() else "❌ Not running"
    formatter_status = "✅ Running" if check_formatter_service() else "❌ Not running"
    
    print_with_delay(f"  Timer:     {timer_status}")
    print_with_delay(f"  Reminder:  {reminder_status}")
    print_with_delay(f"  Formatter: {formatter_status}")
    pause()

def main():
    while True:
        clear_screen()
        print(TITLE)
        
        # Check for fired reminders and display them prominently
        fired_reminders = []
        if check_reminder_service():
            fired_reminders = get_fired_habit_reminders()
            if fired_reminders:
                print("\n" + "="*50)
                print("🔔 REMINDER ALERT! 🔔".center(50))
                print("="*50)
                for reminder in fired_reminders:
                    print(f"  {reminder}")
                print("="*50)
                print("\n💡 TIP: Type 'do' to quickly complete these habits!\n")
        
        print(COMMANDS)
        command = input("\nWhat would you like to do? ").lower().strip()
        
        if command in ('q','quit','exit'):
            print_with_delay("\nKeep up the good habits! Goodbye!"); break
        
        # Handle 'do' command
        if command in ('d', 'do'):
            if fired_reminders:
                do_reminded_habit(fired_reminders)
            else:
                print_with_delay("\nNo fired reminders to act on.")
                print_with_delay("Use 'mark' or 'timed' to complete habits manually.")
                time.sleep(2)
            continue
        
        mapping = {
            'n': add_habit, 'new': add_habit,
            'm': mark_habit, 'mark': mark_habit,
            't': timed_habit, 'timed': timed_habit,
            'remind': setup_reminders, 'reminders': setup_reminders,
            'v': view_habits, 'view': view_habits,
            'e': edit_habit, 'edit': edit_habit,
            'r': remove_habit, 'remove': remove_habit,
            'about': about
        }
        fn = mapping.get(command)
        if fn:
            fn(); continue
        print_with_delay("\nI didn't understand that command. Please try again."); time.sleep(1)

if __name__ == "__main__":
    main()
