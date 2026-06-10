import os
import shutil
import urllib.request
import zipfile
import sys
from pathlib import Path

# Paths configuration
REPO_ROOT = Path(__file__).resolve().parent.parent
BALATRO_DIR = REPO_ROOT / "Balatro.v1.0.0i"

if sys.platform == "linux":
    # Under Linux, resolve Wine prefix AppData path
    import subprocess
    wineprefix = os.environ.get("WINEPREFIX", os.path.expanduser("~/.wine"))
    drive_c = Path(wineprefix) / "drive_c"
    
    # Initialize WinePrefix if users directory does not exist yet
    if not (drive_c / "users").exists():
        print(f"Initializing Wine prefix at {wineprefix}...")
        env = os.environ.copy()
        env["WINEPREFIX"] = wineprefix
        env["WINEDEBUG"] = "-all"
        subprocess.run(["wineboot", "-u"], env=env, check=True)
        
    users_dir = drive_c / "users"
    appdata_dir = None
    for p in users_dir.iterdir():
        if p.is_dir() and p.name not in (".", ".."):
            candidate = p / "AppData" / "Roaming"
            if candidate.exists():
                appdata_dir = candidate
                break
            candidate_alt = p / "Application Data"
            if candidate_alt.exists():
                appdata_dir = candidate_alt
                break
                
    if not appdata_dir:
        username = os.environ.get("USER", "steamuser")
        appdata_dir = users_dir / username / "AppData" / "Roaming"
        
    APPDATA_DIR = appdata_dir
else:
    APPDATA_DIR = Path(os.environ.get("APPDATA", r"C:\Users\Thomas\AppData\Roaming"))

BALATRO_APPDATA = APPDATA_DIR / "Balatro"
MODS_DIR = BALATRO_APPDATA / "Mods"

# URLs for required tools
LOVELY_RELEASE_URL = "https://github.com/ethangreen-dev/lovely-injector/releases/download/v0.8.0/lovely-x86_64-pc-windows-msvc.zip"
# Steamodded 1.0.0-beta-1221a branch zip (stable compat with v1.0.0i)
STEAMODDED_ZIP_URL = "https://github.com/Steamopollys/Steamodded/archive/refs/tags/1.0.0-beta-1221a.zip"
# BalatroBot Lua mod repository zip
BALATROBOT_ZIP_URL = "https://github.com/coder/balatrobot/archive/refs/heads/main.zip"

def download_and_extract(url, extract_to, name=""):
    print(f"Téléchargement de {name} depuis {url}...")
    temp_zip = extract_to / "temp_download.zip"
    try:
        urllib.request.urlretrieve(url, temp_zip)
        print(f"Extraction de {name}...")
        with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        os.remove(temp_zip)
        print(f"{name} installé avec succès dans {extract_to}.")
    except Exception as e:
        print(f"Erreur lors de l'installation de {name}: {e}")
        if temp_zip.exists():
            os.remove(temp_zip)
        raise e

def setup_lovely():
    print("--- Configuration de Lovely Injector ---")
    if not BALATRO_DIR.exists():
        print(f"Erreur: Le répertoire du jeu Balatro n'existe pas : {BALATRO_DIR}")
        sys.exit(1)
    
    # Download lovely injector zip to game directory and extract version.dll
    temp_dir = BALATRO_DIR / "lovely_temp"
    temp_dir.mkdir(exist_ok=True)
    
    try:
        download_and_extract(LOVELY_RELEASE_URL, temp_dir, "Lovely Injector")
        # Find version.dll inside temp_dir
        version_dll = temp_dir / "version.dll"
        if not version_dll.exists():
            # Sometimes inside subdirectory
            for p in temp_dir.glob("**/version.dll"):
                version_dll = p
                break
        
        if version_dll.exists():
            shutil.copy(version_dll, BALATRO_DIR / "version.dll")
            print("version.dll copiée à la racine de Balatro avec succès.")
        else:
            print("Erreur: version.dll introuvable dans l'archive Lovely.")
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

def setup_steamodded():
    print("\n--- Configuration de Steamodded ---")
    MODS_DIR.mkdir(parents=True, exist_ok=True)
    smods_dir = MODS_DIR / "smods"
    
    # If already exists, clear it
    if smods_dir.exists():
        shutil.rmtree(smods_dir)
    smods_dir.mkdir(exist_ok=True)
    
    temp_dir = MODS_DIR / "smods_temp"
    temp_dir.mkdir(exist_ok=True)
    
    try:
        download_and_extract(STEAMODDED_ZIP_URL, temp_dir, "Steamodded")
        # Steamodded zip contains a root folder like 'Steamodded-1.0.0-beta-1221a'
        root_dir = next(temp_dir.iterdir())
        for item in root_dir.iterdir():
            shutil.move(str(item), smods_dir / item.name)
        
        # Patch sticker.toml for Balatro v1.0.0i compatibility (rental sticker does not exist in v1.0.0i)
        sticker_toml_path = smods_dir / "lovely" / "sticker.toml"
        if sticker_toml_path.exists():
            print("Applying Balatro v1.0.0i compatibility patch to sticker.toml...")
            sticker_toml_content = sticker_toml_path.read_text(encoding="utf-8")
            fixed_content = sticker_toml_content.replace(
                'pattern = "if v == \'rental\' then*"',
                'pattern = "if v == \'pinned_left\' then*"'
            )
            sticker_toml_path.write_text(fixed_content, encoding="utf-8")
            print("sticker.toml patched successfully.")
            
        # Patch stake.toml for Balatro v1.0.0i compatibility (stake >= 8 does not enable rentals in v1.0.0i)
        stake_toml_path = smods_dir / "lovely" / "stake.toml"
        if stake_toml_path.exists():
            print("Applying Balatro v1.0.0i compatibility patch to stake.toml...")
            stake_toml_content = stake_toml_path.read_text(encoding="utf-8")
            old_patch = """[[patches]]
[patches.pattern]
target = "game.lua"
pattern = "if self.GAME.stake >= 8 then self.GAME.modifiers.enable_rentals_in_shop = true end"
position = "after"
payload = "end SMODS.setup_stake(self.GAME.stake)"
match_indent = true"""
            new_patch = """[[patches]]
[patches.regex]
target = "game.lua"
pattern = '''(?<indent>[\\t ]*)if self\\.GAME\\.stake >= 8 then\\s*(?:self\\.GAME\\.modifiers\\.enable_rentals_in_shop = true\\s*end|.*?\\n[\\t ]*self\\.GAME\\.starting_params\\.hand_size = self\\.GAME\\.starting_params\\.hand_size - 1\\s*\\r?\\n[\\t ]*end)'''
position = "after"
line_prepend = "$indent"
payload = "end SMODS.setup_stake(self.GAME.stake)"\t"""
            normalized_content = stake_toml_content.replace('\r\n', '\n')
            old_patch_normalized = old_patch.replace('\r\n', '\n')
            new_patch_normalized = new_patch.replace('\r\n', '\n')
            fixed_content = normalized_content.replace(old_patch_normalized, new_patch_normalized)
            stake_toml_path.write_text(fixed_content, encoding="utf-8")
            print("stake.toml patched successfully.")
            
        # Patch joker_retriggers.toml for Balatro v1.0.0i compatibility (Yorick event logic)
        joker_retriggers_toml_path = smods_dir / "lovely" / "joker_retriggers.toml"
        if joker_retriggers_toml_path.exists():
            print("Applying Balatro v1.0.0i compatibility patch to joker_retriggers.toml...")
            joker_retriggers_toml_content = joker_retriggers_toml_path.read_text(encoding="utf-8")
            old_patch = """# Yorick
[[patches]]
[patches.pattern]
target = "card.lua"
pattern = "self.ability.yorick_discards = self.ability.yorick_discards - 1"
position = "after"
match_indent = true
payload = "return nil, true\""""
            new_patch = """# Yorick
[[patches]]
[patches.pattern]
target = "card.lua"
pattern = "self.ability.yorick_discards = self.ability.yorick_discards - 1"
position = "after"
match_indent = true
payload = "do return nil, true end\""""
            normalized_content = joker_retriggers_toml_content.replace('\r\n', '\n')
            old_patch_normalized = old_patch.replace('\r\n', '\n')
            new_patch_normalized = new_patch.replace('\r\n', '\n')
            fixed_content = normalized_content.replace(old_patch_normalized, new_patch_normalized)
            joker_retriggers_toml_path.write_text(fixed_content, encoding="utf-8")
            print("joker_retriggers.toml patched successfully.")
            
        # Patch game_object.lua for Balatro v1.0.0i compatibility (G.COLLABS is nil in v1.0.0i)
        game_object_path = smods_dir / "src" / "game_object.lua"
        if game_object_path.exists():
            print("Applying Balatro v1.0.0i compatibility patch to game_object.lua...")
            game_object_content = game_object_path.read_text(encoding="utf-8")
            collabs_patch = """function loadAPIs()
    if not G.COLLABS then
        G.COLLABS = {
            options = {
                Hearts = {'default_Hearts'},
                Clubs = {'default_Clubs'},
                Diamonds = {'default_Diamonds'},
                Spades = {'default_Spades'}
            },
            pos = {},
            colour_palettes = setmetatable({}, {
                __index = function(t, k)
                    return {}
                end
            })
        }
    end
    if G.localization and G.localization.misc then
        G.localization.misc.collabs = G.localization.misc.collabs or {}
        G.localization.misc.collab_palettes = G.localization.misc.collab_palettes or {}
        G.localization.misc.quips = G.localization.misc.quips or {}
    end
    if G.SETTINGS then
        G.SETTINGS.CUSTOM_DECK = G.SETTINGS.CUSTOM_DECK or { Collabs = {} }
        G.SETTINGS.colour_palettes = G.SETTINGS.colour_palettes or {}
    end"""
            normalized_content = game_object_content.replace('\r\n', '\n')
            fixed_content = normalized_content.replace("function loadAPIs()", collabs_patch)
            
            old_skin_block = """                local skin = self.obj_table[G.SETTINGS.CUSTOM_DECK.Collabs[k]]
                local pal = G.SETTINGS.colour_palettes[k]
                if not skin.outdated and skin.palette_map and not skin.palette_map[pal] then
                    G.SETTINGS.colour_palettes[k] = skin.palettes[1].key
                end"""
            new_skin_block = """                local skin = self.obj_table[G.SETTINGS.CUSTOM_DECK.Collabs[k]]
                if skin then
                    local pal = G.SETTINGS.colour_palettes[k]
                    if not skin.outdated and skin.palette_map and not skin.palette_map[pal] then
                        G.SETTINGS.colour_palettes[k] = skin.palettes[1].key
                    end
                end"""
            fixed_content = fixed_content.replace(old_skin_block.replace('\r\n', '\n'), new_skin_block.replace('\r\n', '\n'))
            
            game_object_path.write_text(fixed_content, encoding="utf-8")
            print("game_object.lua patched successfully.")
            
        # Patch card_limit.toml for Balatro v1.0.0i compatibility (local hand_space pattern differs)
        card_limit_toml_path = smods_dir / "lovely" / "card_limit.toml"
        if card_limit_toml_path.exists():
            print("Applying Balatro v1.0.0i compatibility patch to card_limit.toml...")
            card_limit_toml_content = card_limit_toml_path.read_text(encoding="utf-8")
            fixed_content = card_limit_toml_content.replace(
                'pattern = "local hand_space = e or*"',
                'pattern = "local hand_space = math.min(#G.deck.cards, G.hand.config.card_limit - #G.hand.cards)"'
            )
            card_limit_toml_path.write_text(fixed_content, encoding="utf-8")
            print("card_limit.toml patched successfully.")
            
        print("Steamodded configuré dans le dossier Mods/smods.")
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

def setup_balatrobot_mod():
    print("\n--- Configuration du Mod BalatroBot ---")
    bot_mod_dir = MODS_DIR / "balatrobot"
    if bot_mod_dir.exists():
        shutil.rmtree(bot_mod_dir)
    bot_mod_dir.mkdir(exist_ok=True)
    
    temp_dir = MODS_DIR / "balatrobot_temp"
    temp_dir.mkdir(exist_ok=True)
    
    try:
        download_and_extract(BALATROBOT_ZIP_URL, temp_dir, "BalatroBot Repo")
        # Repo has a root folder like 'balatrobot-main'
        root_dir = next(temp_dir.iterdir())
        
        # We need to copy files from the mod's LUA files directory:
        # According to BalatroBot documentation:
        # We need balatrobot.json, balatrobot.lua, and the src/lua/ directory copied to Mods/balatrobot/
        
        # In github repo, the mod files are directly in the root or a subfolder?
        # Let's inspect the files or move the whole content of the mod subfolder.
        # Actually, coder/balatrobot is a python package AND a lua mod.
        # Let's look at the structure of the repo. We will copy:
        # - balatrobot.lua
        # - balatrobot.json
        # - src/ folder (contains lua files if any)
        
        # Let's copy the entire contents of the cloned repo to the mod folder for simplicity,
        # or structure it specifically.
        # We can look at what's in the repo.
        # Let's copy:
        #   balatrobot.lua
        #   balatrobot.json
        #   src/ (recursive)
        
        shutil.copy(root_dir / "balatrobot.lua", bot_mod_dir / "balatrobot.lua")
        shutil.copy(root_dir / "balatrobot.json", bot_mod_dir / "balatrobot.json")
        
        # Copy the src directory if it exists and has lua files
        src_lua_src = root_dir / "src"
        if src_lua_src.exists():
            shutil.copytree(src_lua_src, bot_mod_dir / "src")

        # Patch settings.lua for speed hack and FPS cap
        settings_lua_path = bot_mod_dir / "src" / "lua" / "settings.lua"
        if settings_lua_path.exists():
            print("Applying BalatroBot settings.lua speed hack patch...")
            content = settings_lua_path.read_text(encoding="utf-8").replace('\r\n', '\n')
            
            # Replace configure_love_update delta time
            old_update = 'local dt = BB_SETTINGS.headless and (4.99 / 60.0) or (1.0 / 60.0)'
            new_update = 'local dt = BB_SETTINGS.headless and (49.9 / 60.0) or (10.0 / 60.0) -- 10x Speed Hack'
            content = content.replace(old_update, new_update)
            
            # Replace configure_fast to support G.SETTINGS.GAMESPEED = 100.0 and FPS throttling
            old_fast = """local function configure_fast()
  -- performance
  G.FPS_CAP = nil -- Unlimited FPS
  G.SETTINGS.GAMESPEED = 10 -- 10x game speed
  G.ANIMATION_FPS = 60 -- 6x faster animations
  G.F_VERBOSE = false
end""".replace('\r\n', '\n')
            new_fast = """local function configure_fast()
  -- performance
  G.FPS_CAP = BB_SETTINGS.fps_cap or 250 -- VSync throttling
  G.SETTINGS.GAMESPEED = 100.0 -- 100x speed hack
  G.SETTINGS.gamespeed = 100.0
  G.ANIMATION_FPS = 600
  G.F_VERBOSE = false
end""".replace('\r\n', '\n')
            content = content.replace(old_fast, new_fast)
            settings_lua_path.write_text(content, encoding="utf-8")
            print("settings.lua patched successfully.")

        # Patch start.lua for clean resets and clearing unlock events
        start_lua_path = bot_mod_dir / "src" / "lua" / "endpoints" / "start.lua"
        if start_lua_path.exists():
            print("Applying BalatroBot start.lua patch...")
            content = start_lua_path.read_text(encoding="utf-8")
            target = "G.FUNCS.setup_run({ config = {} })"
            replacement = "G.FUNCS.setup_run({ config = {} })\n    if G.E_MANAGER and G.E_MANAGER.queues and G.E_MANAGER.queues.unlock then\n      G.E_MANAGER.queues.unlock = {}\n    end\n    G.FUNCS.exit_overlay_menu()"
            if target in content and replacement not in content:
                content = content.replace(target, replacement)
                start_lua_path.write_text(content, encoding="utf-8")
                print("start.lua patched successfully.")

        # Patch play.lua to avoid brittle UI-bound checks during ROUND_EVAL
        play_lua_path = bot_mod_dir / "src" / "lua" / "endpoints" / "play.lua"
        if play_lua_path.exists():
            print("Applying BalatroBot play.lua ROUND_EVAL bypass patch...")
            content = play_lua_path.read_text(encoding="utf-8").replace('\r\n', '\n')
            
            target_block = """        if G.STATE == G.STATES.ROUND_EVAL then
          -- Early exit if basic conditions not met
          if not G.round_eval or not G.STATE_COMPLETE or G.CONTROLLER.locked then
            return false
          end

          -- Game is won
          if G.GAME.won then
            sendDebugMessage("Return play() - won", "BB.ENDPOINTS")
            local state_data = BB_GAMESTATE.get_gamestate()
            send_response(state_data)
            return true
          end

          -- Wait for first scoring row (blind1) to be added to the UI
          -- This ensures the main scoring events have started processing
          local has_blind1 = G.round_eval:get_UIE_by_ID("dollar_blind1") ~= nil

          -- Wait for cash_out_button to ensure the last scoring row (bottom) has been processed
          local has_cash_out_button = false
          for _, b in ipairs(G.I.UIBOX) do
            if b:get_UIE_by_ID("cash_out_button") then
              has_cash_out_button = true
              break
            end
          end

          -- Both first and last scoring rows must be present
          if has_blind1 and has_cash_out_button then
            local state_data = BB_GAMESTATE.get_gamestate()
            sendDebugMessage("Return play() - cash out", "BB.ENDPOINTS")
            send_response(state_data)
            return true
          end
        end"""
            
            replacement_block = """        if G.STATE == G.STATES.ROUND_EVAL then
          if G.round_eval and G.STATE_COMPLETE and not G.CONTROLLER.locked then
            local state_data = BB_GAMESTATE.get_gamestate()
            sendDebugMessage("Return play() - cash out", "BB.ENDPOINTS")
            send_response(state_data)
            return true
          end
        end"""
            
            if target_block in content:
                content = content.replace(target_block, replacement_block)
                play_lua_path.write_text(content, encoding="utf-8")
                print("play.lua patched successfully.")
            else:
                print("Warning: target_block not found in play.lua")

         # Patch balatrobot.lua to override create_unlock_overlay, bypass unlock popups, and disable rendering
        balatrobot_lua_path = bot_mod_dir / "balatrobot.lua"
        if balatrobot_lua_path.exists():
            print("Applying BalatroBot balatrobot.lua bypass patch...")
            content = balatrobot_lua_path.read_text(encoding="utf-8")
            bypass_code = """
-- Suppress "LONG DT" spam caused by the 10x Speed Hack dt override
local original_print = print
local lua_unpack = unpack or table.unpack
print = function(...)
  local args = {...}
  if #args > 0 and type(args[1]) == "string" and (args[1]:sub(1, 7) == "LONG DT" or args[1]:find("LONG DT")) then
    return
  end
  original_print(lua_unpack(args))
end

-- Bypass unlock popups to prevent the game/API from hanging during automated bot training
local original_create_unlock_overlay = create_unlock_overlay
create_unlock_overlay = function(key)
  sendInfoMessage("Bypassing unlock overlay popup for key: " .. tostring(key), "BB.MOD")
  if G then
    G.SETTINGS.paused = false
    if G.CONTROLLER then
      G.CONTROLLER.locked = false
    end
    if G.E_MANAGER and G.E_MANAGER.queues and G.E_MANAGER.queues.unlock then
      G.E_MANAGER.queues.unlock = {}
    end
  end
end

-- Force Love2D à ignorer la perte de focus sous Xvfb
if love.window then
  love.window.hasFocus = function() return true end
  love.window.isMinimized = function() return false end
  love.window.isVisible = function() return true end
end

-- Désactive l'exécution du pipeline de dessin
love.draw = function() end

-- Court-circuite la présentation de la frame à l'écran virtuel
love.graphics.present = function() end

-- Optionnel : force le moteur à ignorer la création de fenêtre si possible
love.conf = function(t)
    t.window = false
end

-- Force VSync off always
if love.window then
    local old_setMode = love.window.setMode
    love.window.setMode = function(width, height, flags)
        if flags then flags.vsync = 0 end
        return old_setMode(width, height, flags)
    end

    local old_updateMode = love.window.updateMode
    love.window.updateMode = function(width, height, flags)
        if flags then flags.vsync = 0 end
        return old_updateMode(width, height, flags)
    end
end

-- Mock love.audio and disable sound/music functions to prevent Wine/OpenAL hanging on headless Linux
if love.audio then
  love.audio.play = function() end
  love.audio.stop = function() end
  love.audio.pause = function() end
  love.audio.newSource = function()
    local mock_source = {}
    mock_source.play = function() end
    mock_source.stop = function() end
    mock_source.setVolume = function() end
    mock_source.setPitch = function() end
    mock_source.isPlaying = function() return false end
    mock_source.release = function() end
    mock_source.setLooping = function() end
    mock_source.isLooping = function() return false end
    mock_source.clone = function() return mock_source end
    return mock_source
  end
end

-- Override global audio triggers
play_sound = function() end
PLAY_SOUND = function() return { sound = love.audio.newSource() } end


-- Hook into love.update to force gamespeed, apply cash_out fallback, and force instant Moveable updates
local original_love_update = love.update
local cash_out_hooked = false
local moveable_hooked = false
love.update = function(dt)
  if G and G.SETTINGS then
    G.SETTINGS.gamespeed = 100.0
    G.SETTINGS.GAMESPEED = 100.0
  end
  
  -- Periodically clear unlock queues and unlock controller if stuck
  if G and G.E_MANAGER and G.E_MANAGER.queues and G.E_MANAGER.queues.unlock and #G.E_MANAGER.queues.unlock > 0 then
    sendInfoMessage("Active unlock queue detected during update (size: " .. #G.E_MANAGER.queues.unlock .. "). Clearing and unlocking...", "BB.MOD")
    G.E_MANAGER.queues.unlock = {}
    G.SETTINGS.paused = false
    if G.CONTROLLER then
      G.CONTROLLER.locked = false
    end
  end
  if G and G.FUNCS and G.FUNCS.cash_out and not cash_out_hooked then
    local original_cash_out = G.FUNCS.cash_out
    G.FUNCS.cash_out = function(e)
      if not G.round_eval then
        sendInfoMessage("G.round_eval is nil during cash_out, creating dummy to allow state transition", "BB.MOD")
        G.round_eval = {
          alignment = { offset = {} },
          remove = function() end
        }
      end
      original_cash_out(e)
    end
    cash_out_hooked = true
  end
  if Moveable and not moveable_hooked then
    local original_move_xy = Moveable.move_xy
    local moveable_logged = false
    Moveable.move_xy = function(self, dt_param)
      if BB_SETTINGS and BB_SETTINGS.headless then
        if not moveable_logged then
          sendInfoMessage("[DIAGNOSTIC] Moveable.move_xy easing bypass active", "BB.MOD")
          moveable_logged = true
        end
        self.VT.x = self.T.x
        self.VT.y = self.T.y
        self.velocity.x = 0
        self.velocity.y = 0
      else
        original_move_xy(self, dt_param)
      end
    end

    local original_move_scale = Moveable.move_scale
    Moveable.move_scale = function(self, dt_param)
      if BB_SETTINGS and BB_SETTINGS.headless then
        self.VT.scale = self.T.scale
        self.velocity.scale = 0
      else
        original_move_scale(self, dt_param)
      end
    end

    local original_move_r = Moveable.move_r
    Moveable.move_r = function(self, dt_param, vel)
      if BB_SETTINGS and BB_SETTINGS.headless then
        self.VT.r = self.T.r
        self.velocity.r = 0
      else
        original_move_r(self, dt_param, vel)
      end
    end

    moveable_hooked = true
  end
  original_love_update(dt)
end

-- Hook EventManager:update to multiply delta time by 10x for resolving animations instantly
if EventManager then
  local old_event_update = EventManager.update
  local event_manager_logged = false
  EventManager.update = function(self, dt, forced)
    if not event_manager_logged then
      sendInfoMessage("[DIAGNOSTIC] EventManager.update 10x speed multiplier active", "BB.MOD")
      event_manager_logged = true
    end
    return old_event_update(self, dt * 10.0, forced)
  end
end
"""
            if "Bypassing unlock overlay popup" not in content:
                content = content + bypass_code
                balatrobot_lua_path.write_text(content, encoding="utf-8")
                print("balatrobot.lua patched successfully.")

        # Create Lovely .toml patch to fix fresh Wine prefix crashes.
        # This injects code directly into game.lua at source level (before any Lua runs),
        # so it cannot be overwritten by Steamodded at runtime.
        # Fixes: game.lua:1509: attempt to index field 'tutorial_progress' (a nil value)
        lovely_patch_dir = bot_mod_dir / "lovely"
        lovely_patch_dir.mkdir(parents=True, exist_ok=True)
        fresh_prefix_toml = lovely_patch_dir / "fresh_prefix_fix.toml"
        fresh_prefix_toml.write_text('''[manifest]
version = "1.0.0"
dump_lua = true
priority = -1

# Fresh Wine prefix fix: initialize G.SETTINGS.tutorial_progress early
# in Game:start_up(), before any code accesses it.
# The old approach tried to match 'function Game:main_menu(change_context)'
# but that line has a trailing comment in v1.0.0i, causing the pattern to fail.

# Patch 1: Initialize tutorial_progress after set_profile_progress() in Game:start_up()
[[patches]]
[patches.pattern]
target = "game.lua"
pattern = "set_profile_progress()"
position = "after"
match_indent = true
payload = """
    -- [BalatroBot] Guard for fresh Wine prefix with no saved profile
    G.SETTINGS.tutorial_complete = true
    G.SETTINGS.tutorial_progress = {
        completed_parts = {
            shop = true,
            blind = true,
            joker = true,
            hand = true,
            booster = true,
            voucher = true,
            interest = true,
            discard = true,
            play = true,
        },
        hold_parts = {}
    }"""

# Patch 2: Nil-guard the tutorial_progress access in Game:main_menu (line ~1480)
[[patches]]
[patches.pattern]
target = "game.lua"
pattern = "if (not G.SETTINGS.tutorial_complete) and G.SETTINGS.tutorial_progress.completed_parts['big_blind'] then G.SETTINGS.tutorial_complete = true end"
position = "at"
match_indent = true
payload = "if (not G.SETTINGS.tutorial_complete) and G.SETTINGS.tutorial_progress and G.SETTINGS.tutorial_progress.completed_parts and G.SETTINGS.tutorial_progress.completed_parts['big_blind'] then G.SETTINGS.tutorial_complete = true end"

# Patch 3: Nil-guard the tutorial_progress access in Game:start_run (line ~2113)
[[patches]]
[patches.pattern]
target = "game.lua"
pattern = """self.GAME.pseudorandom.seed = args.seed or (not (G.SETTINGS.tutorial_complete or G.SETTINGS.tutorial_progress.completed_parts['big_blind']) and "TUTORIAL") or random_string(8, G.CONTROLLER.cursor_hover.T.x*0.33411983 + G.CONTROLLER.cursor_hover.T.y*0.874146 + 0.412311010*G.CONTROLLER.cursor_hover.time)"""
position = "at"
match_indent = true
payload = """self.GAME.pseudorandom.seed = args.seed or (not (G.SETTINGS.tutorial_complete or (G.SETTINGS.tutorial_progress and G.SETTINGS.tutorial_progress.completed_parts and G.SETTINGS.tutorial_progress.completed_parts['big_blind'])) and "TUTORIAL") or random_string(8, G.CONTROLLER.cursor_hover.T.x*0.33411983 + G.CONTROLLER.cursor_hover.T.y*0.874146 + 0.412311010*G.CONTROLLER.cursor_hover.time)"""
''', encoding="utf-8")
        print("Created Lovely patch: fresh_prefix_fix.toml")
            
        print("Mod BalatroBot Lua installé dans Mods/balatrobot.")
    except Exception as e:
        print(f"Erreur lors du déploiement du Mod BalatroBot: {e}")
        # Let's list files to debug if copy failed
        if temp_dir.exists():
            print("Contenu du dépôt téléchargé :")
            for p in temp_dir.glob("**/*"):
                if p.is_file():
                    print("-", p.relative_to(temp_dir))
        raise e
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    setup_lovely()
    setup_steamodded()
    setup_balatrobot_mod()
    print("\n=== INSTALLATION TERMINÉE AVEC SUCCÈS ===")
    print("Veuillez lancer Balatro.exe pour vérifier que Lovely Injector charge bien Steamodded et BalatroBot.")
