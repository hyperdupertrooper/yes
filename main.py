import discord
from discord import app_commands
from discord.ext import commands, tasks
import random
import string
import os
import json
from datetime import datetime, timedelta
from keep_alive import keep_alive

# Keep the bot alive
keep_alive()

# Set up intents
intents = discord.Intents.default()
intents.members = True  # Needed to manage roles and members
intents.message_content = True

# Create the bot instance
bot = commands.Bot(command_prefix="!", intents=intents)

# Global variables for generated and redeemed keys
generated_keys = []
redeemed_keys = {}  # Dictionary to store redeemed keys with user ID as key
trial_expiration = {}  # Store trial expiration dates
lifetime_keys = {}  # Store users who have lifetime keys

# Event to notify us when the bot is ready
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')
    try:
        await bot.tree.sync()  # Syncs the slash commands
        print("Slash commands synced.")
    except Exception as e:
        print(f"Error syncing commands: {e}")

    check_trial_expiration.start()  # Start the trial expiration check

# Function to generate a random alphanumeric string of length 64
def generate_random_key():
    characters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(characters) for _ in range(64))

# Save generated keys to a text file
def save_key_to_file(key):
    with open("keys.txt", "a") as f:
        f.write(f"{key}\n")

def load_redeemed_keys():
    try:
        with open("redeemed_keys.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_redeemed_keys(redeemed_keys):
    with open("redeemed_keys.json", "w") as f:
        json.dump(redeemed_keys, f, indent=4)

# Load available keys from a text file
def load_keys_from_file():
    if os.path.exists("keys.txt"):
        with open("keys.txt", "r") as f:
            return [line.strip() for line in f.readlines()]
    return []

# Initialize the redeemed_keys dictionary
redeemed_keys = load_redeemed_keys()

# Check if the user is the server owner
def is_server_owner(interaction):
    return interaction.user.id == interaction.guild.owner_id

# Command to generate keys
@bot.tree.command(name="genkeys", description="Generate Keys")
@app_commands.describe(count="Number of keys to generate")
async def genkeys(interaction: discord.Interaction, count: int):
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("No permission Idiot", ephemeral=False)
        return
    keys = [generate_random_key() for _ in range(count)]
    with open("keys.txt", "a") as f:
        for key in keys:
            f.write(f"{key}\n")
    await interaction.response.send_message(f"Generated {count} keys.", ephemeral=True)

@bot.tree.command(name="findkey", description="Find user data associated with a specific key.")
@app_commands.describe(key="The key to find the associated user")
async def findkey(interaction: discord.Interaction, key: str):
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("No permission Idiot", ephemeral=False)
        return
    try:
        with open("redeemed_keys.json", "r") as f:
            redeemed_keys = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        redeemed_keys = {}

    # Look for the key in the redeemed_keys
    user_data = None
    for user_id, data in redeemed_keys.items():
        if data["key"] == key:
            user_data = {
                "user_id": user_id,
                "expiration": data.get("expiration", "No expiration"),
                "key": data["key"]
            }
            break

    if user_data is None:
        await interaction.response.send_message("Key not found or has not been redeemed.", ephemeral=True)
        return

    # Retrieve user object for sending the embed
    user = interaction.guild.get_member(int(user_data["user_id"]))

    # Create an embed to display user data
    embed = discord.Embed(title=f"User Data for Key: {user_data['key']}", color=discord.Color.blue())
    embed.add_field(name="User", value=f"{user.mention if user else 'Unknown User'}", inline=False)
    embed.add_field(name="Key", value=user_data["key"], inline=False)
    embed.add_field(name="Expiration", value=user_data["expiration"], inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="redeem", description="Redeem an available key.")
@app_commands.describe(key="The key to redeem.")
async def redeem(interaction: discord.Interaction, key: str):
    # Load redeemed keys and available keys
    redeemed_keys = load_redeemed_keys()
    keys = load_keys_from_file()

    # Check if the key has already been redeemed
    if any(info['key'] == key for info in redeemed_keys.values()):
        await interaction.response.send_message("This key has already been redeemed.", ephemeral=True)
        return

    # Validate key and assign Buyer role
    if key in keys:
        buyer_role = discord.utils.get(interaction.guild.roles, name="Buyer")
        if buyer_role:
            await interaction.user.add_roles(buyer_role)
            expiration_str = "Never"  # For lifetime

            # Remove key from available keys and update file
            keys.remove(key)
            save_keys(keys)

            # Add redeemed key to redeemed_keys.json
            redeemed_keys[str(interaction.user.id)] = {
                "key": key,
                "expiration": expiration_str,
                "is_trial": False
            }
            save_redeemed_keys(redeemed_keys)

            await interaction.response.send_message("Successfully redeemed your key and assigned Buyer role.", ephemeral=True)
        else:
            await interaction.response.send_message("Buyer role not found.", ephemeral=True)
    else:
        await interaction.response.send_message("Invalid key.", ephemeral=True)

@bot.tree.command(name="trial", description="Grant trial access to a user.")
@app_commands.describe(member="Member to give trial access", days="Duration of the trial in days")
async def trial(interaction: discord.Interaction, member: discord.Member, days: int):
    # Owner check
    if not is_server_owner(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    # Load keys and choose a random one for trial
    keys = load_keys_from_file()
    if not keys:
        await interaction.response.send_message("No keys available.", ephemeral=True)
        return

    # Select and remove key, save available keys
    trial_key = keys.pop(0)
    save_keys(keys)

    # Calculate trial expiration
    expiration_date = datetime.now() + timedelta(days=days)
    expiration_str = expiration_date.strftime("%Y-%m-%d %H:%M:%S")

    # Assign Buyer role and update redeemed keys
    buyer_role = discord.utils.get(interaction.guild.roles, name="Buyer")
    if buyer_role:
        await member.add_roles(buyer_role)
        redeemed_keys = load_redeemed_keys()
        redeemed_keys[str(member.id)] = {
            "key": trial_key,
            "expiration": expiration_str,
            "is_trial": True
        }
        save_redeemed_keys(redeemed_keys)
        await interaction.response.send_message(f"Trial access granted to {member.mention} for {days} days.", ephemeral=True)
    else:
        await interaction.response.send_message("Buyer role not found.", ephemeral=True)

@bot.tree.command(name="lifetime", description="Grant lifetime access to a user.")
@app_commands.describe(member="Member to give lifetime access", key="Lifetime key to assign")
async def lifetime(interaction: discord.Interaction, member: discord.Member, key: str):
    # Owner check
    if not is_server_owner(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    # Load available and redeemed keys
    keys = load_keys_from_file()
    redeemed_keys = load_redeemed_keys()

    # Check if the key is valid and has not been redeemed
    if key in keys and not any(info['key'] == key for info in redeemed_keys.values()):
        # Assign Buyer role and update redeemed keys
        buyer_role = discord.utils.get(interaction.guild.roles, name="Buyer")
        if buyer_role:
            await member.add_roles(buyer_role)

            # Remove key from available keys and update file
            keys.remove(key)
            save_keys(keys)

            # Save lifetime access in redeemed_keys.json
            redeemed_keys[str(member.id)] = {
                "key": key,
                "expiration": "Never",
                "is_trial": False
            }
            save_redeemed_keys(redeemed_keys)
            await interaction.response.send_message(f"Lifetime access granted to {member.mention}.", ephemeral=True)
        else:
            await interaction.response.send_message("Buyer role not found.", ephemeral=True)
    else:
        await interaction.response.send_message("Invalid or already redeemed key.", ephemeral=True)

# Command to generate the user's script with their redeemed key
@bot.tree.command(name="myscript", description="Get your script with the redeemed key.")
async def myscript(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    # Check if the user has redeemed a key
    if user_id not in redeemed_keys:
        await interaction.response.send_message("You have not redeemed any keys.", ephemeral=True)
        return

    key_data = redeemed_keys[user_id]
    key = key_data["key"]

    # Create the Lua script with the redeemed key
    lua_script = f'getgenv().key = "{key}"'

    await interaction.response.send_message(f"```lua\n{lua_script}\n```", ephemeral=True)


# Command to get information about a user
@bot.tree.command(name="getinfo", description="Get information about a user")
@app_commands.describe(member="The member to check the key and expiration for")
async def getinfo(interaction: discord.Interaction, member: discord.Member):
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("No permission Idiot", ephemeral=False)
        return

    user_id = str(member.id)
    user_data = redeemed_keys.get(user_id, None)

    if user_data is None:
        await interaction.response.send_message(f"{member.name} has not redeemed any keys.", ephemeral=True)
        return

    key = user_data.get("key", "No key found")
    expiration = user_data.get("expiration", "No expiration")

    # Format expiration message
    if expiration == "Lifetime":
        expiration_message = "Expiring: Never"
    else:
        expiration_message = f"Expiring: {expiration}"

    embed = discord.Embed(title=f"Information for {member.name}", color=discord.Color.blue())
    embed.add_field(name="Key", value=key, inline=False)
    embed.add_field(name="Expiration", value=expiration_message, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

# Background task to check for trial expiration
@tasks.loop(minutes=1)
async def check_trial_expiration():
    current_time = datetime.utcnow()
    for user_id, expiration in list(trial_expiration.items()):
        if current_time >= expiration:
            guild = bot.get_guild(YOUR_GUILD_ID)  # Replace with your guild ID
            member = guild.get_member(user_id)
            if member:
                buyer_role = discord.utils.get(guild.roles, name="Buyer")
                await member.remove_roles(buyer_role)
                del trial_expiration[user_id]
                await member.send("Your trial period has expired and the Buyer role has been removed.")
                print(f"Removed Buyer role from {member.name}")

# Save the current list of keys to a file
def save_keys(keys):
    with open("keys.txt", "w") as f:
        for key in keys:
            f.write(f"{key}\n")

bot.run(os.getenv("DISCORD_TOKEN"))
