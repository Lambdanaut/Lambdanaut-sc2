# PROBLEMS AND SOLUTIONS


## BUGS

  * Couldn't take
    * 5th expansion on Cerulean Falls LE.
    * 4th expansion on Stasis LE
    * Kept getting this error in the log over a hundred times in a row:
    * `Build Manager: Couldn't build expansion. All spots are taken.`

  * Make sure priority targets are pathable before attacking them with melee (zergling baneling)
  
## HIGH PRIORITY

  * Disable drone(worker) and expansion build targets while defending if we have a spawning pool/gateway/barracks

  * Zergling/banelings target workers from a distance

  * Don't fly first overlord into cannons at natural. Right now against zoctoss we do that. 

  * Group army groups together using centroids and k-means
    * With this, we can refine micro by getting closer/further than enemy units based on the centroid's dps

  * Remember friendly units so we can figure out if they're being attacked. Like so:
    * https://github.com/Hannessa/sc2-bots/blob/master/cannon-lover/base_bot.py#L334
    
## MEDIUM PRIORITY

  * Keep tags of all seen enemy units

  * Search for further enemy expansions and structures.
    * ForceManager could enter a state of searching for further expansions

  * Add late game builds that are triggered based on scouting info
    * Corruptor BroodLord
    * Ultralisk Corruptor
    
  * Add infestors and infestor micro

  * Add lurker and lurker micro
  
  * Zergling micro. Catch up and surround vulnerable prey
    * A trickier one, but can be done. 

  * Move army in unison towards different targets. Perhaps using sc2.client.query_pathings?
  
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

  * Add baneling drops
    * Upgrade ventrical sacks
    * Upgrade overlord and save its tag
    * Load banelings
    * Move Overlord to nearest corner of map
    * Move Overlord to adjacent corner of map
    * Move Overlord to enemy start location
    * Unload banelings

  * Fix bug where the build order stalls if hatchery cannot be placed in the next_expansion_location. 
    * Maybe write a custom version of next_expansion_location that takes an index to get the expansion location after
      the next expansion location. Use that if building the hatchery fails.  
  
  * Move army closer to enemy army if our units near army center have a higher dps than units near enemy army center

  * Fix bug where worker rallies to spawn a hatchery, then returns to base, then rallies again. 
    * Problem is when we look ahead to the next build target, it sends the worker to build the hatchery
    
  * Fix hatchery placement on some maps. Build closer to the start location via ground-pathing distance

  * Fix spine crawler placement. It's atrocious and is losing us matches!
    * Idea: Place at base with least pathing_distance to the enemy start location :D
    
  * DEFENDING state doesn't defend with banelings. FIX THIS OMG

