"""Deterministic delay-only transport. Payloads are frozen at send time."""
import copy
import heapq
from trust_network.demo.documents import digest


class MessageBus:
    def __init__(self):
        self.tick=0; self.counter=0; self.queue=[]; self.events=[]

    def record(self, kind, **fields):
        body={'kind':kind,'tick':self.tick,'sequence':len(self.events),
              'previous':digest(self.events[-1]) if self.events else None,**copy.deepcopy(fields)}
        self.events.append(body)
        return body

    def send(self,sender,receiver,payload,delay=1,**metadata):
        if type(delay) is not int or delay<0: raise ValueError('invalid delay')
        item={'sender':sender,'receiver':receiver,'payload':copy.deepcopy(payload),**copy.deepcopy(metadata)}
        self.counter+=1
        heapq.heappush(self.queue,(self.tick+delay,self.counter,item))
        self.record('send',message_id=self.counter,**item)

    def until(self,tick,deliver):
        if tick<self.tick: raise ValueError('time cannot run backwards')
        while self.queue and self.queue[0][0]<=tick:
            at,number,item=heapq.heappop(self.queue); self.tick=at
            self.record('delivery',message_id=number,**item)
            deliver(item)
        self.tick=tick
