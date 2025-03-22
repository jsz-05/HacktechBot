import discord
from discord.ext import commands
from discord import app_commands
import os
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# Configure intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Using commands.Bot for hybrid functionality
class VerificationBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.verification_states = {}  # Track user verification states
        
    async def setup_hook(self):
        # Make sure the CSV exists and has the Verified column
        if not os.path.exists(CSV_PATH):
            print(f"Creating new CSV file at {CSV_PATH}")
            df = pd.DataFrame(columns=["First Name", "Last Name", "Email", "Reimbursement", "Verified"])
            df.to_csv(CSV_PATH, index=False)
        else:
            load_participant_data()

bot = VerificationBot()

VERIFICATION_CHANNEL_ID = int(os.getenv('VERIFICATION_CHANNEL_ID'))
VERIFIED_ROLE_ID = int(os.getenv('VERIFIED_ROLE_ID'))
CSV_PATH = "confirmed.csv"

print("Set Verification ID as", VERIFICATION_CHANNEL_ID)
print("Set Verified Role ID as", VERIFIED_ROLE_ID)

# Load participant data from CSV
def load_participant_data():
    try:
        df = pd.read_csv(CSV_PATH)
        # Add Verified column if it doesn't exist
        if "Verified" not in df.columns:
            df["Verified"] = False
            df.to_csv(CSV_PATH, index=False)
        return df
    except Exception as e:
        print(f"Error loading participant data: {e}")
        return pd.DataFrame(columns=["First Name", "Last Name", "Email", "Reimbursement", "Verified"])

# Save updated participant data to CSV
def save_participant_data(df):
    try:
        df.to_csv(CSV_PATH, index=False)
        return True
    except Exception as e:
        print(f"Error saving participant data: {e}")
        return False





@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}.")
    await bot.change_presence(activity=discord.Game(name="Verification"))
    
    # Sync the command tree to register slash commands
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.event
async def on_member_join(member):
    # Get the verification channel
    verification_channel = bot.get_channel(VERIFICATION_CHANNEL_ID)
    
    if verification_channel:
        # Send a message in the verification channel mentioning the new member
        await verification_channel.send(
            f"Welcome {member.mention}! Please use the `/verify` command in this channel to begin verification.",
            delete_after=60
            )







# Email verification command
@bot.tree.command(name="verify", description="Begin the verification process")
async def verify_command(interaction: discord.Interaction):
    # Only allow in verification channel
    if interaction.channel_id != VERIFICATION_CHANNEL_ID:
        await interaction.response.send_message(
            f"Please use this command in the verification channel.", 
            ephemeral=True
        )
        return
    
    # Check if user is already verified
    if interaction.user.id in bot.verification_states and bot.verification_states[interaction.user.id].get("verified", False):
        await interaction.response.send_message(
            "You've already been verified! If you're having issues, please contact an administrator.", 
            ephemeral=True
        )
        return
        
    # Create modal for email input
    class EmailModal(discord.ui.Modal, title="Hacktech Email Verification"):
        email = discord.ui.TextInput(
            label="Email Address",
            placeholder="Enter the email your confirmation was sent to",
            required=True
        )
        
        async def on_submit(self, modal_interaction: discord.Interaction):
            await process_email_verification(modal_interaction, str(self.email))
    
    await interaction.response.send_modal(EmailModal())


async def process_email_verification(interaction, email):
    user_id = interaction.user.id
    email = email.strip().lower()
    
    # Load participant data
    df = load_participant_data()
    
    # Check if email exists in CSV
    matching_rows = df[df["Email"].str.lower() == email]
    
    if matching_rows.empty:
        await interaction.response.send_message(
            "Email was not found in our database. Please try again with the email you registered with (hint: use the email your confirmation was sent to), or email hacktech@caltech.edu with the title 'DISCORD VERIFICATION ISSUE' if you need assistance.",
            ephemeral=True
        )
        return
    
    # Check if already verified
    if matching_rows["Verified"].values[0]:
        await interaction.response.send_message(
            "This email has already been used to verify a user. Email hacktech@caltech.edu with the title 'DISCORD VERIFICATION ISSUE' if you need assistance",
            ephemeral=True
        )
        return
    
    # Store verification state
    first_name = matching_rows["First Name"].values[0]
    last_name = matching_rows["Last Name"].values[0]
    reimbursement = matching_rows["Reimbursement"].values[0]
    
    bot.verification_states[user_id] = {
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "reimbursement": reimbursement,
        "confirmed": False,
        "row_index": matching_rows.index[0],
        "verified": False
    }
    
    # Create confirmation buttons
    class ConfirmView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=300)  # 5 minute timeout
            
        @discord.ui.button(label="Yes, that's me", style=discord.ButtonStyle.green)
        async def confirm_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
            if button_interaction.user.id != user_id:
                await button_interaction.response.send_message("This verification is not for you. Try again or email hacktech@caltech.edu with the title 'DISCORD VERIFICATION ISSUE' if you need assistance", ephemeral=True)
                return
                
            await process_confirmation(button_interaction)
            
        @discord.ui.button(label="No, that's not me", style=discord.ButtonStyle.red)
        async def deny_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
            if button_interaction.user.id != user_id:
                await button_interaction.response.send_message("This verification is not for you. Try again or email hacktech@caltech.edu with the title 'DISCORD VERIFICATION ISSUE' if you need assistance", ephemeral=True)
                return
                
            # Clear verification state
            if user_id in bot.verification_states:
                del bot.verification_states[user_id]
                
            await button_interaction.response.send_message(
                "Verification cancelled. Please try the `/verify` command again with the correct email.",
                ephemeral=True
            )
    
    # Send confirmation message with buttons
    await interaction.response.send_message(
        f"Are you {first_name} {last_name}?",
        view=ConfirmView(),
        ephemeral=True
    )

async def process_confirmation(interaction):
    user_id = interaction.user.id
    
    if user_id not in bot.verification_states:
        await interaction.response.send_message(
            "Please start the verification process again using the `/verify` command.",
            ephemeral=True
        )
        return
    
    verification_data = bot.verification_states[user_id]
    
    if verification_data.get("confirmed", False):
        await interaction.response.send_message(
            "You've already confirmed your identity. Please wait while I complete the verification process.",
            ephemeral=True
        )
        return
    
    # Mark as confirmed
    verification_data["confirmed"] = True
    
    # Set the user's nickname to their first and last name
    try:
        guild = interaction.guild
        member = guild.get_member(user_id)
        
        if member:
            full_name = f"{verification_data['first_name']} {verification_data['last_name']}"
            await member.edit(nick=full_name)
            nickname_set = True
        else:
            nickname_set = False
    except discord.Forbidden:
        print(f"Missing permissions to set nickname for user {user_id}")
        nickname_set = False
    except Exception as e:
        print(f"Error setting nickname for user {user_id}: {e}")
        nickname_set = False
    
    # Create final confirmation buttons for reimbursement
    class FinalConfirmView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=300)  # 5 minute timeout
            
        @discord.ui.button(label="Complete Verification", style=discord.ButtonStyle.green)
        async def complete_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
            if button_interaction.user.id != user_id:
                await button_interaction.response.send_message("This verification is not for you.", ephemeral=True)
                return
                
            # Complete verification process
            try:
                # Get the guild and role
                guild = interaction.guild
                verified_role = guild.get_role(VERIFIED_ROLE_ID)
                
                # Get the member object
                member = guild.get_member(user_id)
                
                if member and verified_role:
                    # Add role
                    await member.add_roles(verified_role)
                    
                    # Update CSV
                    df = load_participant_data()
                    df.at[verification_data["row_index"], "Verified"] = True
                    save_participant_data(df)
                    
                    # Mark as fully verified
                    verification_data["verified"] = True
                    
                    # Confirmation message
                    await button_interaction.response.send_message(
                        "✅ Verification complete! You now have access to the Hacktech 2025 Discord. Welcome aboard!",
                        ephemeral=True
                    )
                else:
                    await button_interaction.response.send_message(
                        "I couldn't assign your role. Please contact an director for help.",
                        ephemeral=True
                    )
            except Exception as e:
                print(f"Error during verification: {e}")
                await button_interaction.response.send_message(
                    "An error occurred during verification. Please contact a director for assistance.",
                    ephemeral=True
                )
    
    # Send reimbursement status with final button
    reimbursement_status = verification_data["reimbursement"]
    
    # Add message about nickname change
    nickname_message = ""
    if nickname_set:
        nickname_message = f"Your server nickname has been set to '{verification_data['first_name']} {verification_data['last_name']}'.\n\n"
    else:
        nickname_message = "I couldn't set your nickname due to permissions. An admin may update it later.\n\n"
    
    await interaction.response.send_message(
        f"{nickname_message}Just to confirm, your eligibility for travel reimbursement is '{reimbursement_status}'.\n\nClick 'Complete Verification' to complete the process and gain access to the server.",
        view=FinalConfirmView(),
        ephemeral=True
    )

# Admin command to reload CSV
@bot.tree.command(name="reload", description="Admin command to reload participant data from CSV")
@app_commands.default_permissions(administrator=True)
async def reload_csv(interaction: discord.Interaction):
    """Admin command to reload the participant data from CSV"""
    try:
        load_participant_data()
        await interaction.response.send_message("Participant data reloaded successfully!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Error reloading participant data: {e}", ephemeral=True)



# Run the bot with token from .env file
bot.run(os.getenv('TOKEN'))