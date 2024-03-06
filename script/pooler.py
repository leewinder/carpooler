''' Script to create car pools for traveling to an event'''
import os
import googlemaps

from collections import defaultdict
from typing import Dict, List, Optional
from datetime import datetime
from datetime import timedelta

MAX_CAR_POOL_SIZE = 5  # Global variable for maximum car pool size

MAX_CAR_POOL_RADIUS = 10 # Global variable for maximum distance (in miles) between post codes in a car pool
MIN_CAR_POOL_RADIUS = 0.5 # Global variable for starting distance check (in miles) between post codes in a car pool
CAR_POOL_RADIUS_STEP = 0.5 # Global variable for the step size to increase the radius by

class Player:   # pylint: disable=too-few-public-methods
    ''' Defines the properties of a player '''
    def __init__(self, name: str, seats_taken: int, post_code: str, is_driver: bool, group_id: int, must_drive: bool):
        self.name = name
        self.seats_taken = seats_taken
        self.post_code = post_code
        self.is_driver = is_driver
        self.group_id = group_id
        self.must_drive = must_drive

class Event:   # pylint: disable=too-few-public-methods
    ''' Defines the properties of the event we're going to '''
    def __init__(self, event_post_code: str, event_address: str, event_name: str, start_time: str):
        self.event_post_code = event_post_code
        self.event_address = event_address
        self.event_name = event_name
        self.start_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M")

class EventData:
    def __init__(self, players: List[Player], event_details: Event):
        self.players = players
        self.event_details = event_details


class Distance:
    ''' Contains information about distances between two post codes '''
    def __init__(self, source: str, destination: str, distance: float):
        self.source = source
        self.destination = destination
        self.distance = distance

class PostCodeInfo:
    ''' Information about each post code so we can group players '''
    def __init__(self, post_code: str, highest_group_id: int):
        self.post_code = post_code
        self.highest_group_id = highest_group_id
        self.distance_to_event: Distance = None
        self.distance_to_others: Dict[str, Distance] = {}
        self.players: List[Player] = []
        self.count = 0
        self.has_driver = False
        self.travel_time: TravelTime = None

class TravelTime:
    ''' Contains information about the travel time between two post codes '''
    def __init__(self, time_to_next: int, expected_pickup_time: datetime):
        self.time_to_next = time_to_next
        self.expected_pickup_time = expected_pickup_time


class CarPool:
    ''' Properties about an individual car pool '''
    def __init__(self, post_code_info: List[PostCodeInfo]):
        self.post_code_info = post_code_info
        self.driver:Player = None
        self.group_id = post_code_info[0].highest_group_id

    def total_people(self) -> int:
        total = 0
        for info in self.post_code_info:
            total += info.count
        return total


def create_google_api_client() -> googlemaps.Client:
    ''' Returns the Google API token we use for the maps API '''

    file_path = 'input/google_token.txt'
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File '{file_path}' not found.")

    with open(file_path, 'r', encoding="utf-8") as file:
        token = file.readline().strip()
        return googlemaps.Client(key=token)


def load_event_data() -> EventData:
    ''' Loads the event data file containing information about players and destinations'''

    file_path = 'input/event.txt'
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File '{file_path}' not found.")

    players = []
    section = None
    event_post_code = None
    event_address = None
    event_name = None
    start_time = None

    with open(file_path, 'r', encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line == 'Players':
                section = 'Players'
            elif line == 'Details':
                section = 'Details'
            elif line.startswith('-') or len(line.strip()) == 0:
                continue
            elif section == 'Players' and line:
                player_data = line.split(':')
                player = Player(player_data[0].strip(), int(player_data[1].strip()), player_data[2].strip().replace(' ', ''), True if player_data[3].strip().lower() == "true" else False, int(player_data[4].strip()), True if player_data[5].strip().lower() == "true" else False)
                players.append(player)
            elif section == 'Details' and line:
                data = line.split(':', 1)
                if data[0].strip() == 'Event Post Code':
                    event_post_code = data[1].strip().replace(' ', '')
                elif data[0].strip() == 'Event Address':
                    event_address = data[1].strip()
                elif data[0].strip() == 'Event Name':
                    event_name = data[1].strip()
                elif data[0].strip() == 'Start Time':
                    start_time = data[1].strip()
    return EventData(players, Event(event_post_code, event_address, event_name, start_time))


def prepare_post_codes(event_data: EventData, google_maps_client: googlemaps.Client) -> Dict[str, PostCodeInfo]:
    ''' Returns information about each post code so we can start to group people '''
    post_code_info = defaultdict(lambda: PostCodeInfo(post_code=None, highest_group_id=0))

    for player in event_data.players:
        post_code = player.post_code

        post_code_info[post_code].post_code = post_code
        post_code_info[post_code].players.append(player)
        post_code_info[post_code].count += player.seats_taken
        post_code_info[post_code].highest_group_id = max(post_code_info[post_code].highest_group_id, player.group_id)
        if player.is_driver:
            post_code_info[post_code].has_driver = True

    # Now we have the post codes, we need to get the distance of them all to the event
    post_codes = []
    for post_code in post_code_info:
        post_codes.append(post_code)

    # Get all the distances and add them to the post code info so we have distances between everyone and the destination
    distance_to_events = calculate_distance_between_postcodes(post_codes, [event_data.event_details.event_post_code]+post_codes, google_maps_client)

    for post_code, this_distance in distance_to_events.items():
        for this_destination in this_distance:
            if this_destination.destination == event_data.event_details.event_post_code:
                post_code_info[post_code].distance_to_event = this_destination
            else:
                post_code_info[post_code].distance_to_others[this_destination.destination] = this_destination

    return dict(post_code_info)


def calculate_distance_between_postcodes(sources: List[str], destinations: List[str], google_maps_client: googlemaps.Client) -> Dict[str, List[Distance]]:
    ''' Returns the distance between two post codes in miles using the Google Maps package '''

    # Get all the distances and then return them paired with each source
    # Since we're limited to 100 elements per request, we need to make multiple requests but try and make as few as possible

    # How many elements in source can we send in one request - this will not work if we have >100 people traveling 0_o
    MAX_ELEMENTS = 100
    maximum_sources_size = MAX_ELEMENTS // len(destinations)

    combined_results = None
    for i in range(0, len(sources), maximum_sources_size):
        result = google_maps_client.distance_matrix(sources[i:i+maximum_sources_size], destinations, units='imperial', mode='driving')
        if combined_results is None:
            combined_results = result
        else:
            # Combine the results
            combined_results['origin_addresses'] += result['origin_addresses']
            combined_results['rows'] += result['rows']

    # Since the Maps API modifies the post code to create a complete address, we need to use the source list to store the distances
    def get_distance_from_result(result, source_index, destination_index) -> float:
        ''' Returns the distance between two post codes from the Google Maps API result '''

         # Get the distance element from the result
        distance_element = result['rows'][source_index]['elements'][destination_index]

        # Check if the distance element is valid
        if distance_element['status'] != 'OK':
            raise ValueError(f"Failed to get distance between {result['origin_addresses'][source_index]} and {result['destination_addresses'][destination_index]}")

        # Extract the distance in miles
        distance = distance_element['distance']['text']
        distance_in_miles = float(distance.replace('mi', '').strip()) if 'mi' in distance else 0.0

        return distance_in_miles

    distances: Dict[str, List[Distance]] = defaultdict(list)
    for source_index, this_source in enumerate(sources):
        distances[this_source] = []
        for destination_index, this_destination in enumerate(destinations):
            distance = get_distance_from_result(combined_results, source_index, destination_index)
            distances[this_source].append(Distance(this_source, this_destination, distance))

    return distances


def group_identified_players_in_car_pools(post_codes: Dict[str, PostCodeInfo]) -> List[CarPool]:
    ''' Looks for any players with a specific group ID and groups them together in a car pool '''

    car_pools: List[CarPool] = []
    assigned_post_codes: List[str] = []

    # Go through all the post codes and see if we can group them together based on the group IDs
    for post_code_info in post_codes.values():

        # 0 is a none value group ID so ignore those
        if post_code_info.highest_group_id != 0 and post_code_info.post_code not in assigned_post_codes:
            current_pool = CarPool([post_code_info])
            assigned_post_codes.append(post_code_info.post_code)

            # See if any other post code contains the same group ID
            for other_post_code_info in post_codes.values():
                if other_post_code_info.highest_group_id == post_code_info.highest_group_id and other_post_code_info.post_code not in assigned_post_codes:

                    # We still have to be able to fit them in the car
                    if current_pool.total_people() + other_post_code_info.count <= MAX_CAR_POOL_SIZE:
                        current_pool.post_code_info.append(other_post_code_info)
                        assigned_post_codes.append(other_post_code_info.post_code)
            car_pools.append(current_pool)

    # Send back any car pools we've created
    return car_pools



def add_reaming_players_to_car_pools(post_codes: Dict[str, PostCodeInfo], existing_car_pools: List[CarPool]) -> List[CarPool]:
    ''' Takes the current car pools list and adds all remaining players '''

    # Sort the post code info into order based off the distance to the event, with the furthest away first
    sorted_post_code_info = sorted(post_codes.values(), key=lambda x: x.distance_to_event.distance, reverse=True)

    # We need to incrementally increase the radius so we force the car pools to be as close as possible
    current_radius_check = MIN_CAR_POOL_RADIUS
    while current_radius_check <= MAX_CAR_POOL_RADIUS:

        for this_post_code in sorted_post_code_info:

            # Look for an existing pool, otherwise create a new one
            current_pool = get_car_pool_for_post_code(this_post_code.post_code, existing_car_pools)
            if current_pool is None:
                current_pool = CarPool([this_post_code])
                existing_car_pools.append(current_pool)

            # Check if we have space for anyone else
            if current_pool.total_people() == MAX_CAR_POOL_SIZE:
                continue

            # Go through all the other post codes, and if they're close enough, and we have space, add them to the pool
            # Since we need to keep checking for the next nearest one, we need to do multiple loops
            looking_for_post_codes = True
            while looking_for_post_codes:

                # Assume we are no longer looking
                looking_for_post_codes = False

                # Are we done since we've filled up our car pool?
                if current_pool.total_people() == MAX_CAR_POOL_SIZE:
                    break

                nearest_post_code = None
                for post_code, distance in this_post_code.distance_to_others.items():

                    # Don't add itself to the pool
                    if post_code == this_post_code.post_code:
                        continue

                    # Don't add one that already exists somewhere else
                    if get_car_pool_for_post_code(post_code, existing_car_pools) is not None:
                        continue

                    # Would this one fit?
                    if current_pool.total_people() + post_codes[post_code].count > MAX_CAR_POOL_SIZE:
                        continue

                    # Is this the closest post code so far, and is it within the radius?
                    if distance.distance <= current_radius_check and (nearest_post_code is None or distance.distance < this_post_code.distance_to_others[nearest_post_code].distance):
                        nearest_post_code = post_code

                # If we found a post code, add it to the pool and keep going...
                if nearest_post_code is not None:
                    if nearest_post_code == "CV24AL":
                        print("Adding post code", nearest_post_code, "to car pool")
                    current_pool.post_code_info.append(post_codes[nearest_post_code])
                    looking_for_post_codes = True

        # Next radius size
        current_radius_check += CAR_POOL_RADIUS_STEP

        # Before we finish, if we're still going to keep looking for post codes, we need to remove any car pools
        # that only have one post code in them, since they need to be added to a wider pool
        # However, only do this if we're not at the maximum radius
        if current_radius_check < MAX_CAR_POOL_RADIUS:
            existing_car_pools = [pool for pool in existing_car_pools if len(pool.post_code_info) > 1]

        # Check if we have any car pools that we can merge together based on the distance between the post codes
        for i in range(len(existing_car_pools)):
            for j in range(i+1, len(existing_car_pools)):
                pool1 = existing_car_pools[i]
                pool2 = existing_car_pools[j]
                for post_code_info1 in pool1.post_code_info:
                    for post_code_info2 in pool2.post_code_info:
                        distance = post_code_info1.distance_to_others[post_code_info2.post_code]
                        if distance.distance <= current_radius_check and pool1.total_people() + post_code_info2.count <= MAX_CAR_POOL_SIZE and pool2.total_people() + post_code_info1.count <= MAX_CAR_POOL_SIZE:
                            pool1.post_code_info.append(post_code_info2)
                            pool2.post_code_info.remove(post_code_info2)
                            break
                    if not pool2.post_code_info:
                        break
                if not pool1.post_code_info:
                    break

        # Remove any empty car pools
        existing_car_pools = [pool for pool in existing_car_pools if pool.post_code_info]

    # Send the modified car pools list back
    return existing_car_pools


def get_car_pool_for_post_code(post_code: str, car_pools: List[CarPool]) -> Optional[CarPool]:
    ''' Checks if a post code has been assigned to a car pool and returns the car pool if found '''
    for pool in car_pools:
        for post_code_info in pool.post_code_info:
            if post_code_info.post_code == post_code:
                return pool
    return None


def assign_drivers(car_pools: List[CarPool]) -> List[CarPool]:

    ''' Assigns the driver to each car pool, and ensures each car pool has one '''
    for pool in car_pools:

        # Get all the drivers from this post code
        driver_capable_post_code = [post_code for post_code in pool.post_code_info if post_code.has_driver]
        if driver_capable_post_code:
            # Check if there are any players with must_drive set to true
            must_drive_players = [player for post_code_info in driver_capable_post_code for player in post_code_info.players if player.must_drive]

            if must_drive_players:
                if len(must_drive_players) > 1:
                    raise Exception("Multiple players with must_drive set to true. Cannot assign a single driver.")
                else:
                    # Assign the player with must_drive as the driver
                    pool.driver = must_drive_players[0]
            else:
                # If there are no players with must_drive, assign the driver based on the original logic
                furthest_post_code_with_driver = max(driver_capable_post_code, key=lambda driver_capable_post_code: driver_capable_post_code.distance_to_event.distance)

                # Go through the drivers in this post code and assign the first one we find
                for player in furthest_post_code_with_driver.players:
                    if player.is_driver:
                        pool.driver = player
                        break
        else:
            raise Exception("No driver available for car pool.")

    return car_pools


def order_car_pool_pickups(car_pools: List[CarPool]) -> List[CarPool]:
    ''' Orders the car pools so the driver is picked up first, followed by the other players in decreasing distance to the event '''
    for pool in car_pools:
        if pool.driver:
            # Find the index of the post code that contains the assigned driver
            driver_post_code_index = None
            for i, post_code_info in enumerate(pool.post_code_info):
                if post_code_info.post_code == pool.driver.post_code:
                    driver_post_code_index = i
                    break

            # Move the post code with the assigned driver to the front of the list
            if driver_post_code_index is not None:
                pool.post_code_info.insert(0, pool.post_code_info.pop(driver_post_code_index))

            # Sort the remaining post codes based on distance from the event in decreasing order
            pool.post_code_info[1:] = sorted(pool.post_code_info[1:], key=lambda post_code_info: post_code_info.distance_to_event.distance, reverse=True)

    return car_pools

def create_car_pool_routes(car_pools: List[CarPool], google_maps_client: googlemaps.Client, event: Event) -> List[CarPool]:
    ''' Goes through the car pools and plots the expected route for each car pool '''

    for pool in car_pools:
        # Calculate the time needed between each post code to pick up each post code group
        waypoints = [post_code_info.post_code for post_code_info in pool.post_code_info if post_code_info.post_code != pool.driver.post_code]

        source = pool.driver.post_code
        destination = event.event_post_code
        directions_result = google_maps_client.directions(source, destination, waypoints=waypoints)

        # Check the numbers are right - but understand the legs includes the destination not the source
        if len(directions_result[0]['legs']) != len(pool.post_code_info):
            raise Exception(f"Number of legs ({len(directions_result[0]['legs'])}) does not equal the number of post codes ({len(pool.post_code_info)})")

        pickup_time = event.start_time
        for index, leg in reversed(list(enumerate(directions_result[0]['legs']))):
            duration_to_destination = leg['duration']['value'] + 600  # Add 10 minutes for pick up time
            pickup_time -= timedelta(seconds=duration_to_destination)
            travel_time = TravelTime(duration_to_destination, pickup_time)

            # Assign the travel time to the post code info in reverse order
            pool.post_code_info[index].travel_time = travel_time

    return car_pools

def calculate_trip_recommendation(car_pools: List[CarPool], google_maps_client: googlemaps.Client, event: Event) -> List[CarPool]:
    ''' Calculates a recommended trip order for each car pool based on who is driving and the distance to the event '''
    car_pools = order_car_pool_pickups(car_pools)
    return create_car_pool_routes(car_pools, google_maps_client, event)



def print_car_pools(car_pools: List[CarPool], event_details: Event) -> None:
    ''' Prints the car pools to the console '''

    section_title_colour = "\033[31m"
    car_pool_title_colour = "\033[32m"
    car_pool_driver_colour = "\033[33m"
    car_pool_pickup_colour = "\033[33m"
    car_pool_default_colour = "\033[37m"

    print()
    print()
    print()
    print()
    print(section_title_colour + "-----------------------------")
    print(section_title_colour + "|        CAR POOLING        |")
    print(section_title_colour + "-----------------------------")
    print(car_pool_default_colour + f"Car pools to arrive at {event_details.event_name} for {event_details.start_time.strftime('%H:%M')} on {event_details.start_time.strftime('%A %d %B %Y')}")
    print(car_pool_default_colour + f"The full address is {event_details.event_address}")
    print()
    print(car_pool_default_colour + f"Suggested leave and pick up times are based on 10 minutes per pick up and 10 minute buffer for traffic and should be used as a guide only")

    for index, pool in enumerate(car_pools):
        time_to_leave = pool.post_code_info[0].travel_time.expected_pickup_time.strftime('%H:%M')
        print()
        print(car_pool_title_colour + f"Car Pool {index+1}")
        print(car_pool_driver_colour + f"   - Driver:")
        print(car_pool_default_colour + f"      {pool.driver.name} (@{time_to_leave})")
        print(car_pool_pickup_colour + f"   - Pick Ups:")
        for post_code_info in pool.post_code_info:
            if post_code_info != pool.driver:
                pick_up_players = [player.name for player in post_code_info.players if player != pool.driver]
                if pick_up_players:
                    pick_up_time = post_code_info.travel_time.expected_pickup_time.strftime('%H:%M')
                    print(car_pool_default_colour + f"      {', '.join(pick_up_players)} (@{pick_up_time})")

    print()
    print()
    print()
    print()

if __name__ == '__main__':
    google_api_client = create_google_api_client()
    event_details = load_event_data()

    post_code_info = prepare_post_codes(event_details, google_api_client)

    car_pools = group_identified_players_in_car_pools(post_code_info)
    car_pools = add_reaming_players_to_car_pools(post_code_info, car_pools)
    car_pools = assign_drivers(car_pools)

    car_pools = calculate_trip_recommendation(car_pools, google_api_client, event_details.event_details)

    print_car_pools(car_pools, event_details.event_details)






