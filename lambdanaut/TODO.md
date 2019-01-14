# PROBLEMS AND SOLUTIONS

* BUG

  * Sometimes the state will get stuck in "MOVING_TO_ATTACK" but no action will be taken and the game will be stuck in this state

* HIGH PRIORITY

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

  * Search for further enemy expansions and structures.
    * ForceManager could enter a state of searching for further expansions


* MEDIUM PRIORITY
  * Extractors that are depleted shouldn't count as extractors that we own.

  * Deal with hard walls. If an opponent hard-walls, it confuses the AI
    * Need to scout up closer to the base until the wall is seen. Not sure of implementation yet.

  * Banelings should be in front of army during attacks.

  * Attack move to enemy ramp in case of hard walling main

  * Switch from "DEFENDING" state to another where army is pulled home if it seems necessary. Maybe "ALL_DEFENDING"

* LOW PRIORITY

  * Creep spread with queens

  * Prioritize what enemy units to attack with MicroManager. Mutas should focus workers and queens, for instance.

  * Extractor mining blocked/slowed by structure between hatch and extractor
    * Find a build spot that is both near the hatchery and far from geyser/extractors

  * Sending drones to saturate another base when that base is under fire will result in dead drones
    * If the unsaturated base has nearby enemy army units. Don't saturate it

  * A* Algorithm could deal with hard walls and determining if melee units can hit certain units/structures
    * Needs thought and research.

  * Target artosis pylons
    * If a single pylon is visible and there are no known nearby pylons to it. Prioritize attacking pylon

* LOWEST PRIORITY

  * Attack enemy worker scout with multiple drones if he enters the mineral line
    * If enemy worker is between townhall and minerals, attack with up to 10 nearby workers


* DONE

  * Banelings should sometimes attack structures, particularly during hard-wall scenarios

  * Switch between ForceManager states based on conditions

  * Overlord scouting

