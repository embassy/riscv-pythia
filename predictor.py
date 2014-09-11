
from btb import BTB
from ras import RAS
from bht import BHT
import math

class Predictor:

   def __init__(self, w, name ):
      self.name = name
      self.width = w

   def getName(self):
      return self.name

   def predict(self, pc):
      return (False, 0x0)

   def __str__(self):
      return "Predictor (%s)" % self.name

# Model the Rocket front-end, as of 2014 Sept 4 
# Single cycle redirect using the BTB, 
# informed by a gshare BHT and a RAS.
# BTB holds a "is return" bit for RAS popping. 
#
#TODO add sharing the HOB of the PC bits, to allow studying which number of bits to tune to
class RocketPredictor(Predictor):
   
   def __init__(self, w, num_btb_entries, num_ras_entries):
      Predictor.__init__(self, w, "Rocket")
      assert (self.width == 1)
      self.btb = BTB(w, int(num_btb_entries),(0x0, False))
      self.ras = RAS(int(num_ras_entries))
      nbht = 2*int(num_btb_entries)
      self.bht = BHT(nbht, int(math.floor(math.log(nbht, 2))))

   def predict(self, pc):
      bht_pred_taken = self.bht.predict(pc)
      (btb_hit, btb_pred) = self.btb.predict(pc)
      (pred_target, pred_is_ret) = btb_pred
      br_offset = 0
      if (pred_is_ret and not self.ras.isEmpty()):
         return (True, self.ras.pop(), br_offset)
      if (bht_pred_taken and btb_hit): 
         return (True, pred_target, br_offset)
      else: 
         return (False, pc+4, br_offset)

   def update(self, fetch_pc, f_taken, next_pc, commit_bundle, taken_br_offset):
      (pc, taken, target, is_ret, is_call, return_addr) = commit_bundle[0]
      self.btb.update(fetch_pc, f_taken, (target, is_ret))
      self.bht.update(fetch_pc, f_taken)
      if (is_call):
         self.ras.push(return_addr)
      return


# Straw-man design of a future, superscalar Rocket & BOOM
# design is this:
#  BTB: 
#     * updated by Branch Unit in execute (1 a cycle)
#        - only taken branch updates
#        - branch provides its (PC, target, is_ret)
#     * predicted
#        - using an aligned_pc in fetch (mask off bits)  [ WEAK POINT IN DESIGN? ]
#        - provides "br_idx" for blaming which PC is responsible for taken branch
# BHT:
#     * updated in commit (up to W per cycle)
#        - history register must handle multiple branch updates per cycle
#        - 1 n-bit counter per aligned fetch PC (able to be updated by W branches)
# RAS:
#     * predicted 
#        - if BTB returns "is_ret", pop the RAS and take it
#     * updated (is_call) in decode or execute
#        - push the RAS when decode sees a call instruction (PC+4)
#
class SSVer1Predictor(Predictor):
   
   def __init__(self, w, num_btb_entries, num_ras_entries):
      Predictor.__init__(self, w, "SS-Version 1 (full commit info)")
      nbht = 2*int(num_btb_entries)
      # mask to help generate aligned PCs on fetch witdh
      self.shamt = 1 + w
      self.btb = BTB(w, int(num_btb_entries),(0, False, 0))
      self.ras = RAS(int(num_ras_entries))
      self.bht = BHT(nbht, int(math.floor(math.log(nbht, 2))))

   def predict(self, pc):
      aligned_pc = (pc >> self.shamt) << self.shamt
      bht_pred_taken = self.bht.predict(aligned_pc)
      (btb_hit, btb_pred) = self.btb.predict(aligned_pc)
      (pred_target, pred_is_ret, br_offset) = btb_pred
      print "aligned pc: 0x%x ret:%d" % (aligned_pc, pred_is_ret)
      if (pred_is_ret and not self.ras.isEmpty()):
         return (True, self.ras.pop(), br_offset)
      if (bht_pred_taken and btb_hit): 
         return (True, pred_target, br_offset)
      else: 
         return (False, 0, 0)

   def update(self, fetch_pc, taken, next_pc, commit_bundle, taken_br_offset):
      is_ret = False
      found_call = False
      aligned_pc = (fetch_pc >> self.shamt) << self.shamt
      for uop in commit_bundle:
         (pc, taken, target, u_ret, u_call, return_addr) = uop
         self.bht.update(aligned_pc, taken)
         if (u_ret):
            is_ret = True
         if (u_call and not found_call): 
            found_call = True
            self.ras.push(return_addr)

      self.btb.update(aligned_pc, taken, (next_pc, is_ret, taken_br_offset))
      return

