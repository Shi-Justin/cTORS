from planner.planner import Planner
from pyTORS import BeginMoveAction, EndMoveAction, MoveAction, ArriveAction, ExitAction, \
    WaitAction, SetbackAction, SplitAction, CombineAction, TrackPartType
import random

class GreedyPlanner(Planner):
    
    def __init__(self, seed, verbose, config):
        super(GreedyPlanner, self).__init__(seed, verbose, config)
        self.reset()
    
    def get_action(self, state, actions):
        if self.plan is None:
            self.plan = Plan(state, self.location)
        return self.plan.get_action(state, actions)

    def reset(self):
        Planner.reset(self)
        self.plan = None

class Plan:

    def __init__(self, state, location):
        self.location = location
        self.incoming = state.incoming_trains
        self.outgoing = state.outgoing_trains
        self.trains = {}
        available_trains = []
        for inc in self.incoming:
            for tr in inc.shunting_unit.train_units:
                self.trains[tr] = TrainState(tr, inc, location)
                available_trains.append(tr)
        for out in self.outgoing:
            for tr in out.shunting_unit.train_units:
                train = self.find_match(available_trains, tr) if tr not in self.trains else tr
                available_trains.remove(train)
                self.trains[train].update_outgoing(out, tr)
        for train, train_state in self.trains.items():
            train_state.set_same_shunting_unit()
        for train in self.trains:
            self.location.calc_shortest_paths(True, train.type)

    def find_match(self, trains, train):
        for t in trains:
            if t.type == train.type: return t
        return None

    def get_action(self, state, actions):
        for su in state.shunting_units:
            prev = state.get_position(su)
            pos = state.get_previous(su)
            for tr in su.train_units:
                self.trains[tr].update_current_state(prev, pos, su)
        action_priority = sum([train_state.get_action_priority(state, actions) for train_state in self.trains.values()], [])
        action_priority = sorted(action_priority, key=lambda ap: ap[0], reverse=True)
        print(action_priority)
        if(action_priority[0][0] == 0):
            if state.time==1500:
                print("Random!")
            return random.choice(actions)
        return action_priority[0][1]

class TrainState:
    
    def __init__(self, train, incoming, location):
        self.train = train
        self.location = location
        self.incoming = incoming
        self.begin_track = incoming.parking_track
        self.begin_side_track = incoming.side_track
        self.in_su = incoming.shunting_unit
        self.arrival_time = incoming.time
        self.outgoing = None
        self.end_track = None
        self.end_side_track = None
        self.end_su = None
        self.departure_time = None
        self.same_shunting_unit = True

    def update_outgoing(self, outgoing, train_match):
        self.outgoing = outgoing
        self.train_match = train_match
        self.end_track = outgoing.parking_track
        self.end_side_track = outgoing.side_track
        self.out_su = outgoing.shunting_unit
        self.departure_time = outgoing.time

    def update_current_state(self, previous, position, su):
        self.in_su = su
        self.begin_track = position
        self.begin_side_track = previous
        self.set_same_shunting_unit()

    def set_same_shunting_unit(self):
        self.same_shunting_unit = self.in_su.matches_shunting_unit(self.out_su)

    def get_action_priority(self, state, actions):
        su = self.in_su
        priority = [(0, actions[0])]
        if state.time == self.arrival_time:
            TrainState.add_action_if_found(actions, priority, 100, ArriveAction, su)
        if self.same_shunting_unit:
            if state.time >= self.arrival_time and su in state.shunting_units:
                prev = state.get_previous(su)
                pos = state.get_position(su)
                moving = state.is_moving(su)
                if pos == self.end_track and self.end_side_track in pos.get_next_track_parts(prev):
                    if moving: TrainState.add_action_if_found(actions, priority, 5, EndMoveAction, su)
                    else: TrainState.add_action_if_found(actions, priority, 100, ExitAction, su)
                else:
                    if not moving: TrainState.add_action_if_found(actions, priority, 5, BeginMoveAction, su)
                    else:
                        path = self.location.get_shortest_path(self.train.type, prev, pos, self.end_track.get_next_track_parts(self.end_side_track)[0], self.end_track)
                        nextTrack = None
                        nextTrackPrev = pos
                        for track in path.route[1:]:
                            if track.type == TrackPartType.RAILROAD:
                                nextTrack = track
                                break
                            nextTrackPrev = track
                        if not nextTrack is None:
                            if nextTrack == nextTrackPrev: 
                                TrainState.add_action_if_found(actions, priority, 20, SetbackAction, su)   
                            else:
                                TrainState.add_action_if_found(actions, priority, 20, MoveAction, su, track=nextTrack, prev=nextTrackPrev)   
                TrainState.add_action_if_found(actions, priority, 1, WaitAction, su)
        else:
            TrainState.add_action_if_found(actions, priority, 10, SplitAction, su)   
            TrainState.add_action_if_found(actions, priority, 10, CombineAction, self.out_su)
        return priority
    
    @staticmethod
    def add_action_if_found(actions, priority_list, priority, action_type, su, track=None, prev=None):
        action = TrainState.find_action(actions, action_type, su, track, prev)
        if action: priority_list.append((priority, action))

    @staticmethod
    def find_action(actions, action_type, su, track=None, prev=None):
        return next((a for a in actions if isinstance(a, action_type) \
            and (a.shunting_unit == su \
                or (action_type==CombineAction and a.shunting_unit.matches_shunting_unit(su)))\
            and (track is None or a.destination_track == track) \
            and (prev is None or a.previous_track == prev)), None)

