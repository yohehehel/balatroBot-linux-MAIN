#!/usr/bin/env python3
"""
Quick-fix: Create a Lovely .toml patch in the BalatroBot mod directory
to initialize missing profile data on fresh Wine prefixes.

This uses Lovely's source-level patching (injected into game.lua before
any Lua code runs), so it cannot be overwritten by Steamodded at runtime.

Fixes: game.lua:1509: attempt to index field 'tutorial_progress' (a nil value)

Usage:
    python scripts/patch_fresh_prefix.py
"""
import os
import sys
from pathlib import Path

LOVELY_PATCH_CONTENT = '''[manifest]
version = "1.0.0"
dump_lua = true
priority = -1

# Fresh Wine prefix fix: initialize G.SETTINGS.tutorial_progress early
# in Game:start_up(), before any code accesses it.
# The old approach tried to match 'function Game:main_menu(change_context)'
# but that line has a trailing comment in v1.0.0i, causing the pattern to fail.

# Patch 1: Initialize tutorial_progress before set_profile_progress() in Game:start_up()
[[patches]]
[patches.pattern]
target = "game.lua"
pattern = "set_profile_progress()"
position = "before"
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
pattern = \"""self.GAME.pseudorandom.seed = args.seed or (not (G.SETTINGS.tutorial_complete or G.SETTINGS.tutorial_progress.completed_parts['big_blind']) and "TUTORIAL") or random_string(8, G.CONTROLLER.cursor_hover.T.x*0.33411983 + G.CONTROLLER.cursor_hover.T.y*0.874146 + 0.412311010*G.CONTROLLER.cursor_hover.time)\"""
position = "at"
match_indent = true
payload = \"""self.GAME.pseudorandom.seed = args.seed or (not (G.SETTINGS.tutorial_complete or (G.SETTINGS.tutorial_progress and G.SETTINGS.tutorial_progress.completed_parts and G.SETTINGS.tutorial_progress.completed_parts['big_blind'])) and "TUTORIAL") or random_string(8, G.CONTROLLER.cursor_hover.T.x*0.33411983 + G.CONTROLLER.cursor_hover.T.y*0.874146 + 0.412311010*G.CONTROLLER.cursor_hover.time)\"""
'''


def find_balatro_appdata():
    """Find the Balatro AppData in the master Wine prefix."""
    wineprefix = os.environ.get("WINEPREFIX", os.path.expanduser("~/.wine"))
    users_dir = Path(wineprefix) / "drive_c" / "users"
    if not users_dir.exists():
        print(f"Error: Wine users directory not found at {users_dir}")
        sys.exit(1)
    for p in users_dir.iterdir():
        if p.is_dir() and p.name not in (".", ".."):
            for candidate in [p / "AppData" / "Roaming" / "Balatro",
                              p / "Application Data" / "Balatro"]:
                if candidate.exists():
                    return candidate
    return None


def main():
    balatro_dir = find_balatro_appdata()
    if not balatro_dir:
        print("Error: Balatro AppData directory not found. Run setup_mods.py first.")
        sys.exit(1)

    # Create the Lovely patch directory inside balatrobot mod
    balatrobot_lovely_dir = balatro_dir / "Mods" / "balatrobot" / "lovely"
    balatrobot_lovely_dir.mkdir(parents=True, exist_ok=True)

    patch_file = balatrobot_lovely_dir / "fresh_prefix_fix.toml"
    patch_file.write_text(LOVELY_PATCH_CONTENT, encoding="utf-8")
    print(f"Created Lovely patch: {patch_file}")

    # Also clean up the old non-working Lua wrapper if present
    balatrobot_lua = balatro_dir / "Mods" / "balatrobot" / "balatrobot.lua"
    if balatrobot_lua.exists():
        content = balatrobot_lua.read_text(encoding="utf-8")
        if "_bb_orig_main_menu" in content:
            # Remove the old wrapper that doesn't work
            marker = "\n-- Fix for fresh Wine prefix: ensure profile data exists before main_menu accesses it."
            idx = content.find(marker)
            if idx >= 0:
                content = content[:idx]
                balatrobot_lua.write_text(content, encoding="utf-8")
                print("Removed old (non-working) Lua wrapper from balatrobot.lua")
        
        # Inject graphics bypass and VSync override if not already present
        content = balatrobot_lua.read_text(encoding="utf-8")
        bypass_code = """
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

-- Hook into love.update to force gamespeed at every frame
local original_love_update = love.update
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
  original_love_update(dt)
end

-- Hook EventManager:update to multiply delta time by 10x for resolving animations instantly
if EventManager then
  local old_event_update = EventManager.update
  EventManager.update = function(self, dt, forced)
    return old_event_update(self, dt * 10.0, forced)
  end
end
"""
        if "Bypassing unlock overlay popup" not in content:
            content = content + bypass_code
            balatrobot_lua.write_text(content, encoding="utf-8")
            print("balatrobot.lua graphics and VSync bypass patch applied.")

    # Also patch settings.lua inside prefix
    settings_lua_path = balatro_dir / "Mods" / "balatrobot" / "src" / "lua" / "settings.lua"
    if settings_lua_path.exists():
        print("Applying BalatroBot settings.lua speed hack patch in prefix...")
        content = settings_lua_path.read_text(encoding="utf-8")
        
        # Replace configure_love_update delta time
        old_update = 'local dt = BB_SETTINGS.headless and (4.99 / 60.0) or (1.0 / 60.0)'
        new_update = 'local dt = BB_SETTINGS.headless and (49.9 / 60.0) or (10.0 / 60.0) -- 10x Speed Hack'
        content = content.replace(old_update, new_update)
        
        # Replace configure_fast
        old_fast = """local function configure_fast()
  -- performance
  G.FPS_CAP = nil -- Unlimited FPS
  G.SETTINGS.GAMESPEED = 10 -- 10x game speed
  G.ANIMATION_FPS = 60 -- 6x faster animations
  G.F_VERBOSE = false
end"""
        new_fast = """local function configure_fast()
  -- performance
  G.FPS_CAP = BB_SETTINGS.fps_cap or 250 -- VSync throttling
  G.SETTINGS.GAMESPEED = 100.0 -- 100x speed hack
  G.SETTINGS.gamespeed = 100.0
  G.ANIMATION_FPS = 600
  G.F_VERBOSE = false
end"""
        content = content.replace(old_fast, new_fast)
        settings_lua_path.write_text(content, encoding="utf-8")
        print("settings.lua patched successfully in prefix.")

    # Also patch play.lua inside prefix to avoid brittle UI-bound checks during ROUND_EVAL
    play_lua_path = balatro_dir / "Mods" / "balatrobot" / "src" / "lua" / "endpoints" / "play.lua"
    if play_lua_path.exists():
        print("Applying BalatroBot play.lua ROUND_EVAL bypass patch in prefix...")
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
            print("play.lua patched successfully in prefix.")
        else:
            print("Warning: target_block not found in play.lua")

    print("Done! The Lovely patch will inject the fix directly into game.lua at source level.")


if __name__ == "__main__":
    main()
