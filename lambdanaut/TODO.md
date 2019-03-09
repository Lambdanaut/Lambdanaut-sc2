# PROBLEMS AND SOLUTIONS

## NOTES

  * Proxy rax rush for future bot
    * Rush location: 3rd furthest from enemy start location but also off-center from center of map so it's not scouted
    * Build
      * SCV
      * Send first SCV at 0:00
      * Send second SCV at 0:15
      * Supply Depot
      * SCV
      * Barracks
      * Barracks
      * SCV
      * Send 3rd scv. Scout lightly for proxy
      * Marine
      * Marine 
      * (Continue marine production)
      * Send 7 more scv
      * Orbital command
      * bunker at base of enemy ramp. 
      * Pressure enemy ramp with 10 workers and two marines
      * Try to kill as many workers as possible while not losing scv/marine
      * Retreat to bunker if enemy attacks with force and Repair bunker
      * If enemy wall is down, make a bee-line for their mineral line
      * Priority targets
        * Baneling nest, Tech lab on factory, Defensive structures, Pylons, Cybernetics core

  * Rush distances from start location to start location
    * Maps
        * Automaton LE: 157
        * Kairo Junction: 123
        * Parasite LE: 162
        * Cerulean Fall LE: 152
        * Blueshift LE: 138
        * Port Aleksander LE: 166
        * DarknessSanctuaryLE
          * Adjacent spawn: 149
          * Cross spawn: 160
   
    * Average: 150

## BUGS



## HIGH PRIORITY

  * Validate that `unit_is_melee` returns False for melee units.
  
  * Keep overlords away from enemy when they're dispersing
    * If target point is > 20 from overlord
    * Get x points between target point and current point
    * If any enemy units that can attack air are within 10 distance of any of those points
    * Then stop the overlord

  * Keep army together when attacking. Right now zerglings run ahead first. 
  
  * Attack multiple bases with zerglings

  * Switch into 2 base nydus build if we scout multiple banshees and have fewer than 4 townhalls

  * Don't switch to moving_to_attacking if we have an upgrade that is 0.5-0.85% done
   
  * Only spawn creep tumors with non-townhall queens

  * Prefer visible enemies to use bile on. This will prevent us from attempting to bile where we can't see.

  * If we haven't scouted enemy natural expand by the time we take our third, then overlord-scout their natural expand.
    * If we still haven't scouted an enemy natural expand, switch to a 2-base aggressive/defensive build like nydus.

## MEDIUM PRIORITY

  * Use A* when we switch to ATTACKING to hit the enemy where they're most vulnerable
  
  * If we have a baneling nest and we're being attacked with an army greater than ours made of lings, 
    send lings to a corner of main to mutate into banelings. Would defend against hammerbot. 

  * Better baneling vs marine micro. 
    * Have banelings explode on marines before they reach the marine
    * Having banelings explode when they're close enough to the best splash target could be good enough. 

  * Add attention function that keeps army moving towards a target destination during attacks. 
    We want to walk by low priority targets. Would be useful against AdditionalPylons during ravager rushes when the
    ravagers get distracted by a forward Nexus rather than going for probes.

  * Do zergling rushes against zerg on maps with short rush distance
  
  * Do air builds on maps where the rush distance is much shorter than the direct distance (Stasis LE)

  * Write mutalisk micro and re-add mutalisk to ling-bane-muta build

  * Add COUNTERING forces state
    * If the opponent is attacking our base and has more than we have, then attack their main 
      base and don't come back to defend. 

  * Refactor relative_army_strength. It's our slowest function
    * Seems most of the calcs are done in all those `sum` functions. Maybe numpy can speed up sums? 
    * Lots of calc is done in `adjusted_dps` as well. Not sure how much simpler we can make that function...
 
  * Try out Agglomerative Clustering in SKLearn to get better clusters
    * https://hdbscan.readthedocs.io/en/latest/comparing_clustering_algorithms.html#agglomerative-clustering

  * Add 2 base nydus build
    * Add nydus outside enemy natural
    * Add nydus into enemy main
    * Add attack through nydus
    * Add pull all queens through nydus

  * Make use of Pathfinding
    * For Microing around sieged tanks and flanking them
    * For moving-to-attacking
    * For mutalisk micro
  
  * Make midgame rush to brood lords not sucky
  
  * Create an influence map to use for strategizing and micro
    * https://aigamedev.com/open/tutorial/influence-map-mechanics/
    
  * Revisit spine crawler placement after choke detection code has been implemented
  
  * Build a recurrent neural net that learns to micro Mutalisks
    * Goal: Kill as many enemy units as possible before losing all mutalisks

'  * Make sure priority targets are pathable before attacking them with melee (zergling baneling)
    * If priority target is on the other side of a hard wall, zerglings may not attack wall to get to it. 
    * Haven't reproduce this yet. Just a theory
  
  * Turn back overlords if 2 raxes or over 3 marines are scouted with first scout
    * Also enter pool defensive build
  
  * Search for further enemy expansions and structures.
    * ForceManager could enter a state of searching for further expansions

  * Add late game builds that are triggered based on scouting info
    * Corruptor BroodLord
    * Ultralisk Corruptor

  * Add lurker and lurker micro
  
  * Zergling micro. Catch up and surround vulnerable prey
    * A trickier one, but can be done. 

  * Move army in unison towards different targets. Perhaps using sc2.client.query_pathings?
  
## LOW PRIORITY

  * Target artosis pylons
    * If a single pylon is visible and there are no known nearby pylons to it. Prioritize attacking pylon

  * Sending drones to saturate another base when that base is under fire will result in dead drones
    * If the unsaturated base has nearby enemy army units. Don't saturate it

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

  * Disable drone(worker) and expansion build targets while defending if we have a spawning pool/gateway/barracks

  * Group army groups together using centroids and k-means
    * With this, we can refine micro by getting closer/further than enemy units based on the centroid's dps

  * Builds a neural net that calculates which of two armies would win in a fight
    * Input is size 200. First hundred are my units, second hundred are theirs
    * Output is size three. Win, Lose, or Draw

  * Zergling/banelings target workers from a distance
  
  * Remember friendly units so we can figure out if they're being attacked. Like so:
    * https://github.com/Hannessa/sc2-bots/blob/master/cannon-lover/base_bot.py#L334
    
  * Make get_current_target more efficient
    * Skip calling the function if we have less than 25 minerals. Nothing can be built

  * Make overlord scouts not run into photon canons. Turn around if canons sighted.

  * Enter pool defensive build if 2 gateways are scouted with first scout
  
  * Enter pool defensive build if 2 barracks are scouted with first scout
  
  * Enter pool defensive build if 5 zerglings are scouted with first scout
  
  * Make get_current_target more efficient
    * Only call the is_pending function on units we know we'll build. Don't include campaign zerg units

  * Keep tags of all seen enemy units

  * Enter a state PREPARE_TO_DEFEND when we see an enemy army of > 3 units moving out. 
    * Remember each enemy unit and their position
    * If four enemy non-workers/non-overlords take 6 frames of stepping towards our start location, assume an attack and enter PREPARE_TO_DEFEND
    * Halt worker, upgrade, and townhall production. 
    * After 30 seconds, return to HOUSEKEEPING
    * `This would save us from 4:30-6:00 rushes`

  * Don't fly first overlord into cannons at natural. Right now against zoctoss we do that. 
    * `This might be solved? I'm not sure. The code looks fine`

  * Clean up code. Separate managers into their own files. :o

  * Retreat from battles when our cluster is weaker than their cluster

  * Write a better heuristic for determining stronger army compositions
 
  * Integrate remembered enemy units into clusters
  
  * Workers ran to enemy base and hid behind their mineral line what the actual fucking fuck.
    * Has to have something to do with clustering, possibly the DEFENDING state. Perhaps something about moving to the center of a cluster
   
  * Micro infestors behind the cluster they're in
  
  * Fix bile avoidance. Find a way to make bile avoidance a top priority. 
    * We could use pathfinding. But that's really expensive and might not work
    * We could set "is_avoiding_bile" on the cached unit, but that wouldn't be a global solution and it's a big fix
    * We could edit all other micro and movement code in some way so that we avoid biles

  * Test micro on a test map. Get better micro through this.
  
  * Test that burrowing banelings still work after pathfinding integration
  
  * Better defending micro. Need to beat cheezerg's cheezy cheese 
    
  * Add infestors and infestor micro

  * Create a new manager class called DefenseManager that takes over the defending work done by ForceManager. 
    This will allow us to be defending and attacking simultaneously. 

  * Fix Moving To Attack state so that the units move straight to the current Moving to Attack position
  
  * Fix zergling micro so that zerglings don't run from enemies if they're ranged

  * Prioritize minerals that don't have a worker targetting them when sending a worker to mine minerals.
  
  * Send first overlord on a queued path so it intersects the opponent's rush path on its way to their base
    * This way we have a higher chance of scouting zergling cheese.

  * Fix moving_to_attack location. Right now it performs very poorly vs cheezerg because it sends us halfway across
    the map before we attack them. While we're moving out, we get attacked. 
    * We could make the moving-to-attack location towards our base if the enemy structure closer than halfway 
      across the map
      
  * Fix Overlord scouting to work with ravager rushing
  
  * Don't go spore crawlers unless we see two phoenix
  
  * Dont unroot spine crawlers if enemy is nearby where we want to root them
  
  * Add a low-baneling-count zergling build to start vs protoss

  * When defending, defend close to the townhall. No need to leave it. 
    * Attack-move non-busy units to the townhall with the nearest enemy unit

