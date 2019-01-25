# PROBLEMS AND SOLUTIONS


## BUGS


## HIGH PRIORITY

  * Remember friendly units so we can figure out if they're being attacked. Like so:
    * https://github.com/Hannessa/sc2-bots/blob/master/cannon-lover/base_bot.py#L334
  
## MEDIUM PRIORITY

  * Search for further enemy expansions and structures.
    * ForceManager could enter a state of searching for further expansions

  * Add late game builds that are triggered based on scouting info
    * Corruptor BroodLord
    * Ultralisk Corruptor
    
  * Add baneling drops
    * Upgrade ventrical sacks
    * Upgrade overlord and save its tag
    * Load banelings
    * Move Overlord to nearest corner of map
    * Move Overlord to adjacent corner of map
    * Move Overlord to enemy start location
    * Unload banelings

  * Add infestors and infestor micro

  * Add lurker and lurker micro

## LOW PRIORITY

  * Target artosis pylons
    * If a single pylon is visible and there are no known nearby pylons to it. Prioritize attacking pylon

  * Sending drones to saturate another base when that base is under fire will result in dead drones
    * If the unsaturated base has nearby enemy army units. Don't saturate it

  * Switch from "DEFENDING" state to another where all army is pulled home if it seems necessary. Maybe "ALL_DEFENDING"

## LOWEST PRIORITY

  * A* Algorithm could deal with hard walls and determining if melee units can hit certain units/structures
    * Needs thought and research.

  * Deal with hard walls. If an opponent hard-walls, it confuses the AI
    * Need to scout up closer to the base until the wall is seen. Not sure of implementation yet.

  * Attack move to enemy ramp in case of hard walling main


## DONE

  * Banelings should sometimes attack structures, particularly during hard-wall scenarios

  * Switch between ForceManager states based on conditions

  * Overlord scouting

  * Sometimes the state will get stuck in "MOVING_TO_ATTACK" but no action will be taken and the game will be stuck in this state

  * Build orders in a tree structure rather than flat lists. Branches made depending on the state of the game.
      * Changing build order based on scouting information
      * Builds early-game
          * Basic macro-up ( Default )
          * Ling Bane
          * Roach Ravager
      * Builds mid-game:
          * Ling Bane Muta
          * Roach Ravager Hydra
      * Builds late-game

  * Overlord supply doesn't transfer between build orders.

  * Extractors that are depleted shouldn't count as extractors that we own.

  * Creep spread with queens

  * Extractor mining blocked/slowed by structure between hatch and extractor
    * Find a build spot that is both near the hatchery and far from geyser/extractors

  * Build spore crawlers if we scout enemy air or cloak tech

  * Update the amount of army units needed to attack based on the game stage.
    * Early game needs fewer units to do an attack
    * Late game needs more units to do an attack
    * A message can be sent from the BuildManager when the BuildStage changes to let the ForceManager know when to
      update this value

  * Prioritize what enemy units to attack with MicroManager. Mutas should focus workers and queens, for instance.

  * Fix bug where queens sometimes aren't injecting or moving to hatcheries where they're needed
  
  * Banelings should be in front of army during attacks.

  * Fix bug where 2nd expo can't be placed on kairo junction (Fixed by tweakimp)

  * Keep army at closest base to enemy while housekeeping

  * Fix bug where queens aren't transfusing sometimes when they should

