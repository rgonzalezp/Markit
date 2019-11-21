import bpy
from bpy.props import *
import bmesh
import pickle
import math
import mathutils
import json
import requests
from collections import OrderedDict
from scipy.spatial import distance
import threading
import time
import numpy as np

###############################################################################################
####    We define the addon information in this structure:            #########################
####    name,author,version,blender support,location in blender UI,   #########################
####    description,category,etc.                                     #########################
###############################################################################################

bl_info = \
    {
        "name" : "Magic Maker",
        "author" : "Lei Shi <ls776@cornell.edu>, Ricardo Gonzalez <re.gonzalez10@uniandes.edu.co>",
        "version" : (2, 0, 1),
        "blender" : (2, 7, 9),
        "location" : "View 3D > Magic Tools-Maker",
        "description" :"This tool is used to design models for Talkit++, by labelling surfaces in the model",
        "warning" : "",
        "wiki_url" : "",
        "tracker_url" : "",
        "category" : "Development",
}

def writeFile(fileName,data):
    with open(fileName + ".json", 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            
def writeFilePickle(fileName,newdata):
    pickle.dump(newdata, open(fileName, "wb"),
            protocol=2)
    

#get transformation matrix from the Blender coordinates to the Tracker coordinates
def solve_affine( p1, p2, p3, p4, s1, s2, s3, s4 ):
    x = np.transpose(np.matrix([p1,p2,p3,p4]))
    y = np.transpose(np.matrix([s1,s2,s3,s4]))
    x = np.vstack((x,[1,1,1,1]))
    y = np.vstack((y,[1,1,1,1]))
    mtx = y * x.I
    # return function that takes input x and transforms it
    # don't need to return the 4th row as it is
    return mtx

#enter a point X in Blender coordinates, and transformation matrix to get its Tracker coordinates
def solve_point(x, trans):
    result= (trans*np.vstack((np.matrix(x).reshape(3,1),1)))[0:3,:].tolist()
    return [result[0][0],result[1][0],result[2][0]]

#enter a normal X in Blender coordinates, and transformation matrix to get its Tracker coordinates
def solve_normal(x, trans):
    result= (trans*np.vstack((np.matrix(x).reshape(3,1),0)))[0:3,:].tolist()
    return [result[0][0],result[1][0],result[2][0]]

#for initialize the transformation matrix
#calculate the euclidean distance between pt1 and pt2
def calDistance(pt1,pt2):
    return distance.euclidean(pt1,pt2)

#for initialize the transformation matrix
#scale a list with a value (scale)
def calScaledList(scale,list):
    return  [x * scale for x in list]

def faceptsCompare(faceA,faceB):
    for ptA in faceA:
        for ptB in faceB:
            if ptA == ptB:
                return True

    return False
#blenderFace object
#store information for a face
class blenderFace:
    def __init__(self, rawFace, mtx):
        #for marked face, it has more information
        #with the len == 4
        if len(rawFace)==4:
            #makred face
            self.marked=True
            self.blender_index = rawFace[0][0]
            self.label = rawFace[0][1]
            self.content = rawFace[0][2]
            self.gesture = rawFace[0][3]
            self.blender_color = [x * 255 for x in rawFace[1]]
            self.normal = rawFace[3]
            self.verts = rawFace[2]
            self.vertsConverted = []
            self.vertsConverted_2d = []
            self.relatedFaces = []
            for eachPt in self.verts:
                self.vertsConverted.append(solve_point(eachPt, mtx))
            self.normalConverted= solve_normal(self.normal, mtx)
        else:
            #unmarked face
            self.marked = False
            self.verts = rawFace[0]
            self.normal = rawFace[1]
            self.blender_index = rawFace[2]

            self.label = "unmarked"
            self.content = "null"
            self.gesture = "null"
            self.vertsConverted = []
            self.vertsConverted_2d = []
            self.relatedFaces = []
            for eachPt in self.verts:
                self.vertsConverted.append(solve_point(eachPt, mtx))
            self.normalConverted = solve_normal(self.normal, mtx)

#blenderPoint object
#store information for a point
class blenderPoint:
    def __init__(self, coordinates, faceIndex, mtx):
        self.vert = coordinates[:]
        self.faceIndex = [faceIndex]
        self.vertsConverted = solve_point(self.vert, mtx)

    def addFace(self, faceIndex):
        self.faceIndex.append(faceIndex)

#read blender pickle file and save them as blenderFace or blenderPoint
class blenderReader:
    #initialize the reader with the pickle file address
    def __init__(self,fileAddress):
        import datetime
        currentDT = datetime.datetime.now()
        print ("load file" + str(currentDT))
        file = open(fileAddress, "rb")
        #blenderData is encoded as [(xy,yz),(marked face),(unmarked face), (name, introduction)]
        self.data = pickle.load(file)

        self.blenderData = self.data[0]
        file.close()
        print ("finish loading" + str(datetime.datetime.now()))
        #variables for finding the transformation matrix
        self.vertsXZ = self.blenderData[0][0][:]
        self.vertsYZ = self.blenderData[0][1][:]
        self.generalInfo = self.blenderData[3]
        #print self.generalInfo
        #self.unitSize = 14.0/30.0
        self.unitSize = 14.0 / 30.0
        print ("start tranformation matrix" + str(datetime.datetime.now()))
        self.transMtx = self.initialTrans() #no need to check this one
        print ("start marked faces" + str(datetime.datetime.now()))
        self.markedFaces = self.initialMarked()
        print ("start unmarked faces" + str(datetime.datetime.now()))
        self.unmarkedFaces = self.initialUnmarked()
        self.allFaces = self.markedFaces[:]+self.unmarkedFaces[:]
        print ("start related faces" + str(datetime.datetime.now()))
        self.findrelatedFaces()
        print ("finish related faces"+ str(datetime.datetime.now()))
        #self.allPoints = self.getAllpoints()

    def initialTrans(self):
        #identify four key points from the data
        #find the unique one (A) in xz face
        for vertXZ in self.vertsXZ:
            if vertXZ not in self.vertsYZ:
                self.A=vertXZ[:]

        #find the unique one (D) in yz face
        for vertYZ in self.vertsYZ:
            if vertYZ not in self.vertsXZ:
                self.D=vertYZ[:]

        #find the B and C point
        #print self.vertsYZ
        #print self.vertsXZ
        TempResult=[]
        for element in self.vertsXZ:
                if element in self.vertsYZ:
                    TempResult.append(element)
        dis1=calDistance(TempResult[0],self.A)
        dis2=calDistance(TempResult[1],self.A)
        if dis1 > dis2:
            self.B=TempResult[1][:]
            self.C=TempResult[0][:]
        else:
            self.C=TempResult[1][:]
            self.B=TempResult[0][:]

        #print self.A, self.B, self.C, self.D

        #find the real coordinates of these points
        self.ptC=calScaledList(self.unitSize,[-5.04229,0,-8.4463])
        self.ptB=calScaledList(self.unitSize,[-5.04229,0,-8.4463+2.04945])
        self.ptA=calScaledList(self.unitSize,[-5.04229+4.03073,0,-8.4463+2.04945])
        self.ptD=calScaledList(self.unitSize,[-5.04229,4.98983,-8.4463])

        mtx = solve_affine(self.A, self.B, self.C, self.D, self.ptA, self.ptB, self.ptC, self.ptD)
        return mtx

    def initialMarked(self):
        markedFaces=[]
        #Marked face, self.blenderData[1], is encoded as:
        #[[(blender_index, label, content, gesture), blender_color, verts, normal]...]
        for face in self.blenderData[1]:
            markedFaces.append(blenderFace(face, self.transMtx))

        return markedFaces

    def initialUnmarked(self):
        unmarkedFaces=[]
        #Marked face, self.blenderData[1], is encoded as:
        #[[faceVerts, faceNormal]...]
        for face in self.blenderData[2]:
            if len(face[0]) == 3:
                unmarkedFaces.append(blenderFace(face, self.transMtx))
        return unmarkedFaces

    def findrelatedFaces(self):
       faceMap = self.data[1]
       pointMap = self.data[2]
       relatedFaces = {}
       oldIdxToNewIdx = {}
       for face in faceMap:
           if face not in relatedFaces:
               relatedFaces[face] = set()
           for point in faceMap.get(face):
               for fIndex in pointMap.get(point):
                   relatedFaces.get(face).add(fIndex)

       for faceIdx in range(len(self.allFaces)):
           oldIdxToNewIdx[self.allFaces[faceIdx].blender_index] = faceIdx

       for faceIdx in range(len(self.allFaces)):
           faceOldIndex = self.allFaces[faceIdx].blender_index
           tempSet = relatedFaces.get(str(faceOldIndex))
           for faceR in tempSet:
              self.allFaces[faceIdx].relatedFaces.append(oldIdxToNewIdx[faceR])

class cls_AreaData(bpy.types.PropertyGroup):
    bl_options = {'REGISTER', 'UNDO'}
    # The properties for this class which is referenced as an 'entry' below.
    area_index = bpy.props.IntProperty(name="Index", description="index for designated faces", default=0)
    area_label = bpy.props.StringProperty(name="Label", description="Label", default="")
    area_content = bpy.props.StringProperty(name="Content", description="Content", default="")
    area_gesture = bpy.props.StringProperty(name="Gesture", description="Gesture", default="")
    area_color = bpy.props.FloatVectorProperty(
        name="Color",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0, 1.0)
    )

###############################################################################################
####    This class is used to debug errors and                        #########################
####    inform the user about mistakes.                               #########################
####    Pops up a dialog window with the given message                #########################
###############################################################################################

class MessageOperator(bpy.types.Operator):
    
    bl_idname = "error.message"
    bl_label = "Message"
    
    ### Properties set when the error dialog is invoked
    ### type: Type of error
    ### message: Content of the error dialog
    
    type = StringProperty()
    message = StringProperty()

    def execute(self, context):
        self.report({'INFO'}, self.message)
        print(self.message)
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        
        ### Set dialog window size and invoking
        return wm.invoke_popup(self, width=800, height=400)

    def draw(self, context):
        
        ### Defining the structure of the window dialog
        
        self.layout.label("ERROR! Check the message for more info")
        row = self.layout.split(0.25)
        row.prop(self, "type")
        row.prop(self, "message")
        row = self.layout.split(0.80)
        row.label("")
        
        ### Adding ok button to close the window
        
        row.operator("error.ok")

###############################################################################################
####                                                                  #########################
####    The OK button used in the error dialog                        #########################
####                                                                  #########################
###############################################################################################

class OkOperator(bpy.types.Operator):
    bl_idname = "error.ok"
    bl_label = "OK"

    def execute(self, context):
        return {'FINISHED'}


###############################################################################################
####    Make material function                                        #########################
####    This function creates the material that will be used to label##########################
####    the model                                                     #########################
###############################################################################################

def makeMaterial(name, diffuse, alpha, specular=(1, 1, 1)):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = diffuse
    mat.diffuse_shader = 'LAMBERT'
    mat.diffuse_intensity = 1.0
    mat.specular_color = specular
    mat.specular_shader = 'COOKTORR'
    mat.specular_intensity = 0.5
    mat.alpha = alpha
    mat.ambient = 1
    return mat


def mergeObjects(self,context):
    
    obs = []
    scenario = context.scene
    for ob in scenario.objects:
    # whatever objects you want to join...
        if ob.type == 'MESH':
            obs.append(ob)
    ctx = bpy.context.copy()

    # one of the objects to join
    ctx['active_object'] = obs[1]

    ctx['selected_objects'] = obs
    
    # we need the scene bases as well for joining
    ctx['selected_editable_bases'] = [scenario.object_bases[ob.name] for ob in obs]

    bpy.ops.object.join(ctx)
    
    ob = bpy.context.active_object
    
    label = context.scene.inputLabel_hotarea
    color = context.scene.inputColor_hotarea[:]
    content = context.scene.inputContent_hotarea
    gesture = context.scene.inputGesture_hotarea
    i=0
    for i in range(3):
        ob.area_list.add()
        ob.area_list[-1].area_index = 0
        ob.area_list[-1].area_label = "nothing"
        ob.area_list[-1].area_content = "nothing"
        ob.area_list[-1].area_gesture = "nothing"
        ob.area_list[-1].area_color = [0,0,0,0]
        i+=1
    
    print(ob.area_list)
    
    return {"FINISHED"}
    
    
###############################################################################################
####    Add Scaffold function                                           #######################
####    This function creates and adds the tracker scaffold to the scene#######################
####                                                                    #######################
###############################################################################################

def makeScaffold(self,context):
    
    ### Define Scaffold 82 Vertices
    
    Vertices = \
          [
            mathutils.Vector((-29.99028968811035, -6.8105974197387695, -9.081909229280427e-05)),
            mathutils.Vector((-29.99028968811035, -6.8105974197387695, 8.446209907531738)), 
            mathutils.Vector((-29.99028968811035, 10.22175121307373, 8.446209907531738)), 
            mathutils.Vector((-29.99028968811035, 10.22175121307373, -9.081909229280427e-05)),
            mathutils.Vector((-19.942604064941406, -6.8105974197387695, 8.446209907531738)), 
            mathutils.Vector((-19.942604064941406, 10.22175121307373, 8.446209907531738)), 
            mathutils.Vector((-19.942604064941406, -6.8105974197387695, -9.081909229280427e-05)), 
            mathutils.Vector((-19.942604064941406, 10.22175121307373, -9.081909229280427e-05)), 
            mathutils.Vector((-25.95956802368164, 35.02724838256836, 4.396630764007568)), 
            mathutils.Vector((-27.95969009399414, 35.02724838256836, 2.3965096473693848)), 
            mathutils.Vector((-27.95969009399414, 35.02724838256836, 4.396630764007568)), 
            mathutils.Vector((-21.946422576904297, 35.02724838256836, 2.3965096473693848)), 
            mathutils.Vector((-23.894927978515625, 35.02724838256836, 4.396630764007568)), 
            mathutils.Vector((-21.946422576904297, 35.02724838256836, 4.396630764007568)), 
            mathutils.Vector((-25.95956802368164, 35.02724838256836, 6.396751880645752)), 
            mathutils.Vector((-23.894927978515625, 35.02724838256836, 6.396751880645752)), 
            mathutils.Vector((-29.99028968811035, 35.02724838256836, 8.446209907531738)), 
            mathutils.Vector((-29.99028968811035, 35.02724838256836, 6.396751880645752)), 
            mathutils.Vector((-24.948001861572266, 35.02724838256836, 8.446209907531738)), 
            mathutils.Vector((-19.90571403503418, 35.02724838256836, 8.446209907531738)), 
            mathutils.Vector((-19.90571403503418, 35.02724838256836, 6.396751880645752)), 
            mathutils.Vector((-29.99028968811035, 15.067978858947754, 8.446209907531738)), 
            mathutils.Vector((-29.99028968811035, 10.078160285949707, 8.446209907531738)), 
            mathutils.Vector((-24.948001861572266, 10.078160285949707, 8.446209907531738)), 
            mathutils.Vector((-29.99028968811035, 20.057796478271484, 8.446209907531738)), 
            mathutils.Vector((-29.99028968811035, 25.04761505126953, 8.446209907531738)), 
            mathutils.Vector((-29.99028968811035, 30.037431716918945, 8.446209907531738)), 
            mathutils.Vector((-19.90571403503418, 15.067978858947754, 8.446209907531738)), 
            mathutils.Vector((-19.90571403503418, 20.057796478271484, 8.446209907531738)), 
            mathutils.Vector((-19.90571403503418, 25.04761505126953, 8.446209907531738)), 
            mathutils.Vector((-19.90571403503418, 30.037431716918945, 8.446209907531738)), 
            mathutils.Vector((-19.90571403503418, 10.078160285949707, 8.446209907531738)), 
            mathutils.Vector((-19.90571403503418, 15.067978858947754, 6.396751880645752)), 
            mathutils.Vector((-19.90571403503418, 10.078160285949707, 6.396751880645752)), 
            mathutils.Vector((-23.894927978515625, 10.078160285949707, 6.396751880645752)), 
            mathutils.Vector((-23.894927978515625, 15.067978858947754, 6.396751880645752)), 
            mathutils.Vector((-19.90571403503418, 20.057796478271484, 6.396751880645752)),
            mathutils.Vector((-23.894927978515625, 20.057796478271484, 6.396751880645752)),
            mathutils.Vector((-19.90571403503418, 30.037431716918945, 6.396751880645752)),
            mathutils.Vector((-19.90571403503418, 25.04761505126953, 6.396751880645752)), 
            mathutils.Vector((-23.894927978515625, 25.04761505126953, 6.396751880645752)),
            mathutils.Vector((-23.894927978515625, 30.037431716918945, 6.396751880645752)),
            mathutils.Vector((-29.99028968811035, 15.067978858947754, 6.396751880645752)),
            mathutils.Vector((-29.99028968811035, 10.078160285949707, 6.396751880645752)),
            mathutils.Vector((-29.99028968811035, 20.057796478271484, 6.396751880645752)), 
            mathutils.Vector((-29.99028968811035, 30.037431716918945, 6.396751880645752)), 
            mathutils.Vector((-29.99028968811035, 25.04761505126953, 6.396751880645752)), 
            mathutils.Vector((-25.95956802368164, 15.067978858947754, 6.396751880645752)), 
            mathutils.Vector((-25.95956802368164, 10.078160285949707, 6.396751880645752)), 
            mathutils.Vector((-25.95956802368164, 20.057796478271484, 6.396751880645752)), 
            mathutils.Vector((-25.95956802368164, 30.037431716918945, 6.396751880645752)), 
            mathutils.Vector((-25.95956802368164, 25.04761505126953, 6.396751880645752)), 
            mathutils.Vector((-25.95956802368164, 15.067978858947754, 4.396630764007568)), 
            mathutils.Vector((-25.95956802368164, 10.078160285949707, 4.396630764007568)), 
            mathutils.Vector((-25.95956802368164, 20.057796478271484, 4.396630764007568)), 
            mathutils.Vector((-25.95956802368164, 30.037431716918945, 4.396630764007568)), 
            mathutils.Vector((-25.95956802368164, 25.04761505126953, 4.396630764007568)), 
            mathutils.Vector((-27.95969009399414, 15.067978858947754, 4.396630764007568)), 
            mathutils.Vector((-27.95969009399414, 10.078160285949707, 4.396630764007568)), 
            mathutils.Vector((-27.95969009399414, 20.057796478271484, 4.396630764007568)), 
            mathutils.Vector((-27.95969009399414, 30.037431716918945, 4.396630764007568)), 
            mathutils.Vector((-27.95969009399414, 25.04761505126953, 4.396630764007568)), 
            mathutils.Vector((-27.95969009399414, 15.067978858947754, 2.3965096473693848)), 
            mathutils.Vector((-27.95969009399414, 10.078160285949707, 2.3965096473693848)), 
            mathutils.Vector((-27.95969009399414, 20.057796478271484, 2.3965096473693848)), 
            mathutils.Vector((-27.95969009399414, 30.037431716918945, 2.3965096473693848)), 
            mathutils.Vector((-27.95969009399414, 25.04761505126953, 2.3965096473693848)), 
            mathutils.Vector((-21.946422576904297, 15.067978858947754, 2.3965096473693848)), 
            mathutils.Vector((-21.946422576904297, 10.078160285949707, 2.3965096473693848)), 
            mathutils.Vector((-21.946422576904297, 20.057796478271484, 2.3965096473693848)), 
            mathutils.Vector((-21.946422576904297, 30.037431716918945, 2.3965096473693848)), 
            mathutils.Vector((-21.946422576904297, 25.04761505126953, 2.3965096473693848)), 
            mathutils.Vector((-21.946422576904297, 15.067978858947754, 4.396630764007568)), 
            mathutils.Vector((-21.946422576904297, 10.078160285949707, 4.396630764007568)), 
            mathutils.Vector((-21.946422576904297, 20.057796478271484, 4.396630764007568)), 
            mathutils.Vector((-21.946422576904297, 30.037431716918945, 4.396630764007568)), 
            mathutils.Vector((-21.946422576904297, 25.04761505126953, 4.396630764007568)), 
            mathutils.Vector((-23.894927978515625, 15.067978858947754, 4.396630764007568)), 
            mathutils.Vector((-23.894927978515625, 10.078160285949707, 4.396630764007568)), 
            mathutils.Vector((-23.894927978515625, 20.057796478271484, 4.396630764007568)), 
            mathutils.Vector((-23.894927978515625, 30.037431716918945, 4.396630764007568)),
            mathutils.Vector((-23.894927978515625, 25.04761505126953, 4.396630764007568))
          ]
          
    ### Define the mesh we are adding as "Scaffold"
    ### If there is already an item called "Scaffold", it will
    ### automatically add the mesh with the name "Scaffold.001"
    
    NewMesh = bpy.data.meshes.new("Scaffold")
    
    ### We define how the mesh will be built
    ### First we send the Vertices (Defined previously)
    ### Then we send the faces that will compose the Scaffold 
    ### (156 triangular faces), Each face is built by using
    ### 3 of the vertices in the list of vertices given.
    
    NewMesh.from_pydata \
        (
            Vertices,
            [],
            [[23,48,43],[0, 1, 2], [0, 2, 3], [1, 4, 5], [1, 5, 2], [4,6,7], [4,7,5], [6,0,3], [6,3,7], [1,0,6], [6,4,1], [2,7,3], [7,2,5], [8,9,10], [11,9,8], [11,8,12], [13,11,12], [12,8,14], [12,14,15], [18,14,16], [19,20,15], [15,18,19], [18,15,14], [21,22,23], [24,21,23], [24,18,25], [26,18,16], [18,26,25], [24,23,18], [27,28,23], [18,23,28], [18,28,29], [30,18,29], [18,30,19], [31,27,23], [32,33,34], [32,34,35], [36,32,35], [36,35,37], [38,39,40], [38,40,41], [20,38,41], [20,41,15], [39,36,37], [39,37,40], [42,43,22], [21,44,42],[42,22,21], [44,21,24], [45,46,25], [45,25,26], [17,45,26], [46,44,24], [46,24,25], [27,31,33], [27,33,32], [28,27,32], [28,32,36], [30,29,39], [30,39,38], [19,30,38], [19,38,20], [29,28,36], [29,36,39], [47,48,43], [47,43,42], [49,47,42], [49,42,44], [50,51,46], [50,46,45], [14,50,45], [14,45,17], [51,49,44], [51,44,46], [52,53,48], [52,48,47], [54,52,47], [54,47,49], [55,56,51], [55,51,50], [8,55,50], [8,50,14], [56,54,49], [56,49,51], [57,58,53], [57,53,52], [59,57,52], [59,52,54], [60,61,56], [60,56,55], [10,60,55], [10,55,8], [61,59,54], [61,54,56], [62,63,58], [62,58,57], [64,62,57], [64,57,59], [65,66,61], [65,61,60], [9,65,60], [9,60,10], [66,64,59], [66,59,61], [67,68,63], [67,63,62], [69,67,62], [69,62,64], [70,71,66], [70,66,65], [11,70,65], [11,65,9], [71,69,64], [71,64,66], [72,73,68], [72,68,67], [74,72,67], [74,67,69], [75,76,71], [75,71,70], [13,75,70], [13,70,11], [76,74,69], [76,69,71], [77,78,73], [77,73,72], [79,77,72], [79,72,74], [80,81,76], [80,76,75], [12,80,75], [12,75,13], [81,74,76], [35,34,78], [35,78,77], [37,35,77], [37,77,79], [41,40,81], [81,74,79],[41,81,80], [15,41,80], [15,80,12], [40,37,79], [40,79,81], [58,63,53], [63,68,78], [63,78,53], [43,23,22], [48,53,78], [48,78,34], [73,78,68], [31,23,34], [34,23,48], [34,33,31],[16,14,17],[16,26,17]]
        )
    NewMesh.update()
        
    NewObj = bpy.data.objects.new("Scaffold", NewMesh)
    
    ### linking the new object to the scene
    context.scene.objects.link(NewObj)
    
    ### We select the object to add xzFace and yzFace materials
    context.scene.objects.active = NewObj
    
    ob = bpy.context.object                 
    current_mode = bpy.context.object.mode
    
    ### Check in which mode we are to handle errors
    if current_mode != 'EDIT' :
        bpy.ops.object.editmode_toggle()
            
    
    
    # If the material already exists, don't creat a new one
    matxz = bpy.data.materials.get("xzFace")
    matyz = bpy.data.materials.get("yzFace")
    main = bpy.data.materials.new("mainBody")
    if matxz is None:
        # create material if it doesn't exist
        matxz = bpy.data.materials.new(name="xzFace")
        matyz = bpy.data.materials.new(name="yzFace")
        main = bpy.data.materials.new(name="mainBody")
    
    ### Add each of the 3 materials that compose the scaffold     
    ### and give them color
    
    ob.data.materials.append(main)
    
    ### White for the mainbody
    bpy.data.materials['mainBody'].diffuse_color = (1,1,1)
    
    ### Red for the xz plane face
    ob.data.materials.append(matxz)
    bpy.data.materials['xzFace'].diffuse_color = (1,0,0)
    
    ### Blue for the yz plane face
    ob.data.materials.append(matyz)
    bpy.data.materials['yzFace'].diffuse_color = (0,0,1)
        
        
    mesh = ob.data
    
    if bpy.context.object.mode != 'EDIT' :
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.remove_doubles(threshold=0.0001)
        
    bm = bmesh.from_edit_mesh(mesh)
    if hasattr(bm.faces, "ensure_lookup_table"): 
        bm.faces.ensure_lookup_table()
    
    ### We add the materials xzFace and yzFace to 2 specific faces in
    ### the scaffold to have a point of reference.
    
    bm.faces[155].material_index = 2
    bm.faces[154].material_index = 1
        
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_make_consistent(inside=False)
        
        
    bpy.ops.object.editmode_toggle()
        
        
    return {"FINISHED"}


###############################################################################################
####    Tool panel creation class                                    ##########################
####    With this class we create the panel that will have access to ##########################
####    all of our functionalities: Exporting the model to stl,      ##########################
####    labeling each face of the model, decimating the model, adding##########################
####    tracker scaffold                                             ##########################
###############################################################################################

class ToolsPanel(bpy.types.Panel):
    ### We define the name and the location of the tool
    bl_label = "Magic Tools-Marker"
    bl_space_type = "VIEW_3D"
    bl_region_type = "TOOLS"
    bl_category = "MAGIC"

    def draw(self, context):
        layout = self.layout

        ### First we define the section related to model modification
        
        layout.label("MODIFICATION", icon="MATCUBE")
        row = layout.row(align=True)
        box = row.box()
        
        ###Input areas and labels for users
        box.prop(context.scene, "export_model")
        box.prop(context.scene, "export_model_file")
        
        ### Buttons that call for the functionalities
        box.operator("magic.marker", text="Add tracker scaffold").operation = "add"
        box.operator("magic.marker", text="Merge object with tracker scaffold").operation = "merge"
        box.operator("magic.marker", text="Export stl printable model").operation = "stl"
        box.operator("magic.marker", text="Decimate model (simplify)").operation = "decimate"

        ### We add an empty whitespace that separates the sections
        layout.separator()
        
        
        ### We define the section related to the model "face labeling"
        
        layout.label("LABELS", icon="ORTHO")
        row = layout.row(align=True)
        box = row.box()
        
        ###Input areas and labels for users
        box.prop(context.scene, "inputLabel_hotarea")
        box.prop(context.scene, "inputContent_hotarea")
        box.prop(context.scene, "inputGesture_hotarea")
        sub = box.row(True)
        sub.prop(context.scene, "inputColor_hotarea")
        
        
        ### Buttons that call for the functionalities
        box.operator("magic.hotarea", text="confirm").operation = "add"
        box.operator("magic.hotarea", text="Delete selected area").operation = "clean"

        ### We add an empty whitespace that separates the sections
        layout.separator()
        
        ### We define the last section, related to the model export

        layout.label("EXPORT AND IMPORT", icon="FILESEL")
        row = layout.row(align=True)
        box = row.box()
        
        ###Input areas and labels for users
        box.prop(context.scene, "inputName_model")
        box.prop(context.scene, "inputIntroduction_model")
        box.prop(context.scene, "export_path")
        box.prop(context.scene, "import_path")
        
        ### Buttons that call for the functionalities
        box.operator("magic.export", text="export")
        box.operator("magic.import", text="import")
        
        layout.separator()
        
        layout.label("ONLINE MODELS", icon="FILESEL")
        row = layout.row(align=True)
        box = row.box()
        
        box.prop(context.scene, "model_id")
        box.operator("magic.online_import", text = "import")

###############################################################################################
####    MAGIC_marker operator class                                     #######################
####    In this class we define the functions used in the Modification  #######################
####    module: Add Tracker Scaffold, export to stl and decimate the model#####################
###############################################################################################

class MAGIC_marker(bpy.types.Operator):
    bl_idname = "magic.marker"
    bl_label = "Debugger for model modification"
    bl_options = {'REGISTER', 'UNDO'}
    operation = bpy.props.StringProperty()

    def execute(self, context):
        if self.operation == "add":
            makeScaffold(self,context)
            
        if self.operation == "merge":
            mergeObjects(self,context)
            

        if self.operation == "stl":
            path = context.scene.export_model
            filename = context.scene.export_model_file
            if filename == ' ' or path == ' ' :
                bpy.ops.error.message('INVOKE_DEFAULT',
                                      type="Error",
                                      message='You are missing the directory path or the name of the file you are trying to export')

                
            bpy.ops.export_mesh.stl(filepath=path + filename + '.stl')
            print("save stl " + str(time.ctime(int(time.time()))))
            
            
            
        ### We use the error dialog if the user is not selecting a single
        ### object to decimate
        
        if self.operation == "decimate":
            selection = bpy.context.selected_objects
            if len(selection) > 1:
                bpy.ops.error.message('INVOKE_DEFAULT',
                                      type="Error",
                                      message='You selected more than one object')
                return {'FINISHED'}
            if len(selection) == 0:
                bpy.ops.error.message('INVOKE_DEFAULT',
                                      type="Error",
                                      message='Please select one object to decimate')
                return {'FINISHED'}
            bpy.context.scene.objects.active = selection[0]

            mod = selection[0].modifiers.new(name='decimate', type='DECIMATE')
            mod.ratio = 0.1
            bpy.ops.object.modifier_apply(apply_as="DATA", modifier="decimate")


        return {'FINISHED'}

###############################################################################################
####    MAGIC_onlineimport operator class                              ########################
####          #######################
####     #####################
###############################################################################################

class MAGIC_onlineimport(bpy.types.Operator):
    bl_idname = "magic.online_import"
    bl_label = "online import"
    bl_options = {'REGISTER', 'UNDO'}
    operation = bpy.props.StringProperty()

    def execute(self, context):
        selection = bpy.context.selected_objects
        if len(selection) >= 1:
            bpy.ops.error.message('INVOKE_DEFAULT',
                                  type="Error",
                                  message='You select more than one object')
            return {'FINISHED'}

        ## we get the id of the model
        modelid = context.scene.model_id
        
        ## we make the request with the id
        req = requests.get('http://13.59.169.104:8000/api/files/' + modelid + '.json')
        
        
        file = req.json()
        
        ## Copy pasted import method
        data = file
        print(data['vertices'])
        ## Add each vertex to a list - Done
        Vertices = []
        i=0
        for p in data['vertices']:
            p = data['vertices'][str(i)]
            vector = mathutils.Vector((p))
            Vertices.append(vector)
            i+=1
        
        
        ## Add each face to a list - Done
        Faces = []
        i=0
        for f in data['faces']:
            f = data['faces'][str(i)]['vertices']
            Faces.append(f)
            i+=1
        
        ## Use file name to add the new mesh
        NewMesh = bpy.data.meshes.new("whatever")
        
        ### We define how the mesh will be built
        
        ## Use both lists to build the model
        NewMesh.from_pydata \
            (
                Vertices,
                [],
                Faces
            )
        NewMesh.update()
        
        context = bpy.context
        ## Use file name again to link it
        NewObj = bpy.data.objects.new("whatever", NewMesh)
        
        ### linking the new object to the scene
        context.scene.objects.link(NewObj)
        
        ### We select the object to add the materials to the face, and also the areas.
        context.scene.objects.active = NewObj
        
        ob = bpy.context.object 
                        
        current_mode = bpy.context.object.mode
        
        ### Check in which mode we are to handle errors
        if current_mode != 'EDIT' :
            bpy.ops.object.editmode_toggle()
        
        ### Object data
        mesh = ob.data
        
        ### Here we start adding the materials
        
        ##material = makeMaterial(name=p.name, diffuse=p.color, alpha=p.diffuse)
        ##mesh.materials.append(material)
        i=0
        for p in data['materials']:
            ## Change all of this to makeMaterial when doing in main component
            currentData = data['materials'][str(i)]
            material = makeMaterial(name=currentData['name'], diffuse=currentData['color'], alpha=currentData['diffuse'])
            mesh.materials.append(material)
            i+=1
            
        ### Here we start adding the areas
        i=0
        for p in data['areas']:
            currentData = data['areas'][str(i)]
            ob.area_list.add()
            ob.area_list[-1].area_index = currentData['area_index']
            ob.area_list[-1].area_label = currentData['area_label']
            ob.area_list[-1].area_content = currentData['area_content']
            ob.area_list[-1].area_gesture = currentData['area_gesture']
            ob.area_list[-1].area_color = currentData['area_color']
            i+=1
        
        ### Here we paint all the faces depending on their index    
        mesh = ob.data
        
        if bpy.context.object.mode != 'EDIT' :
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.remove_doubles(threshold=0.0001)
            
        bm = bmesh.from_edit_mesh(mesh)
        if hasattr(bm.faces, "ensure_lookup_table"): 
            bm.faces.ensure_lookup_table()
        
        ### We add the materials xzFace and yzFace to 2 specific faces in
        ### the scaffold to have a point of reference.
        i=0
        for f in data['faces']:
            area_index = data['faces'][str(i)]['area_index']
            bm.faces[i].material_index = area_index
            i+=1
            
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent(inside=False)
        
            
            
        bpy.ops.object.editmode_toggle()
        return {'FINISHED'}
        
        
        

###############################################################################################
####    MAGIC_hotarea operator class                                   ########################
####    In this class we define the functions used in the LABELS       #######################
####    module: Add label to faces, delete all labels (need to improve #####################
###############################################################################################

class MAGIC_hotarea(bpy.types.Operator):
    bl_idname = "magic.hotarea"
    bl_label = "Debugger for labelling"
    bl_options = {'REGISTER', 'UNDO'}
    # hotareaInfoStorage = bpy.props.StringProperty()
    operation = bpy.props.StringProperty()

    def execute(self, context):
        selection = bpy.context.selected_objects
        if len(selection) > 1:
            bpy.ops.error.message('INVOKE_DEFAULT',
                                  type="Error",
                                  message='You select more than one object')
            return {'FINISHED'}
        if len(selection) == 0:
            bpy.ops.error.message('INVOKE_DEFAULT',
                                  type="Error",
                                  message='Please select one object')
            return {'FINISHED'}

        if self.operation == "add":
            self.add(context)
        if self.operation == "clean":
            self.clean(context)

        return {'FINISHED'}
    
    
    ### We define the clean function as removing all the areas of the object
    
    def clean(self, context):
        
        ob = bpy.context.active_object
        me = ob.data
        selfaces =[]
        delmaterials =[]
        delareas =[]
        #check for edit mode
        editmode = False
        
        if ob.mode == 'EDIT':
            editmode =True
            #the following sets mode to object by default
            bpy.ops.object.mode_set()
        for f in me.polygons:
            if f.select:
                selfaces.append(f)
        # for f in selfaces:
            # hashSet for material_index
            
        for f in selfaces:
            i = 0
            for a in ob.area_list:
                if f.material_index == a.area_index:
                    if f.material_index not in delmaterials:
                        delmaterials.append(f.material_index)
                        delareas.append(i)
                        delareas.sort()
                        i = i + 1
                    else:
                        i = i + 1
                else:
                    i = i + 1
                
        for f in me.polygons:
            if f.material_index in delmaterials:
                print("changing face", f.index)
                f.material_index = 0
        
        delareas.reverse()
    
        q = 0       
        for j in delareas:
            print(delareas[q])
            ob.area_list[delareas[q]].area_index = 0
            q = q + 1
        
               
        #done editing, restore edit mode if needed
        if editmode:
            bpy.ops.object.mode_set(mode = 'EDIT')
            
        #selection = bpy.context.selected_objects
        #obj = selection[0]
        #for eachareaIndex in range(len(obj.area_list)):
        #    print("clean", eachareaIndex)
        #    obj.area_list.remove(0)
        #mesh = obj.data
        #mesh_editmode = bmesh.from_edit_mesh(mesh)
        #for f in mesh_editmode.faces:
        #    if not f.material_index == 1 and not f.material_index == 2:
        #        f.material_index = 0
        #print(obj.area_list)
        

    def add(self, context):
        selection = bpy.context.selected_objects
        obj = selection[0]
        mesh = obj.data
        
        ### We obtain the inputed values by the user
        ### to determine the name, description, gesture and color
        ### of the faces that the user selected to label
        label = context.scene.inputLabel_hotarea
        color = context.scene.inputColor_hotarea[:]
        content = context.scene.inputContent_hotarea
        gesture = context.scene.inputGesture_hotarea
        
        ### Activate edit mode to add label
        mesh_editmode = bmesh.from_edit_mesh(mesh)

        selected_faces = [p for p in mesh_editmode.faces if p.select]
        
        ### Error management if the user doesn't select at least 1 face
        ### of the model
        if len(selected_faces) == 0:
            bpy.ops.error.message('INVOKE_DEFAULT',
                                  type="Error",
                                  message='Please select at least one polygon')
            return {'FINISHED'}
        
        ### We create a material with the color the user selected
        ### to add the new label
        material = makeMaterial(name=label, diffuse=color[:3], alpha=color[3])
        # create a mesh for the body
        if len(mesh.materials) <= 0:
            mesh.materials.append(makeMaterial(name="mainbody", diffuse=[1, 1, 1], alpha=1.0))

        mesh.materials.append(material)
        current_areas = []
        
        for a in obj.area_list:
            current_areas.append(a.area_index)
           
        
        
        newMaterialIndex = len(mesh.materials) - 1
    
        
        for f in selected_faces:
            
            if newMaterialIndex in current_areas:
                f.material_index = newMaterialIndex  
            else:
                    ### If the selected face is in an area the already exists in the model
                    ### we add it to the area
                obj.area_list.add()
                current_areas.append(newMaterialIndex)
                print("add new area", newMaterialIndex)
                f.material_index = newMaterialIndex
                obj.area_list[-1].area_index = newMaterialIndex
                obj.area_list[-1].area_label = label
                obj.area_list[-1].area_content = content
                obj.area_list[-1].area_gesture = gesture
                obj.area_list[-1].area_color = color
            ### Add a new area and the face to the area list of the model
                    
        print(obj.area_list)
        


###############################################################################################
####    MAGIC_export operator class                                    ########################
####    In this class we define the functions used to export the model ######################
####    module: Export and import                                      #####################
###############################################################################################

class MAGIC_export(bpy.types.Operator):
    bl_idname = "magic.export"
    bl_label = "export"

    def execute(self, context):
        fileName = context.scene.export_path + context.scene.inputName_model
        
        
        data = {}
        obj = bpy.context.active_object  # particular object by name
        mesh = obj.data

        ## Obtaining vertices data
        i = 0
        Vertices = {}

        for vert in mesh.vertices:
            Vertices[i] = [vert.co.x,vert.co.y,vert.co.z]
            i+=1
   
        ## Obtaining faces data
        ## remember to leave edit mode so 
        ## changes reflect on the data <-- very important
        j=0
        Faces = {}

        for face in mesh.polygons:
            currentFace = []
            currentNormal = []
            Faces[j] = {}
            
            for val in face.normal:
                currentNormal.append(val)
            for vert in face.vertices:
                currentFace.append(vert)
                
            Faces[j].update({'vertices':currentFace})
            Faces[j].update({'normal':currentNormal})
            j+=1

        j=0
        for face in mesh.polygons:
            if obj.material_slots[face.material_index].name.startswith('mainBody') or obj.material_slots[face.material_index].name.startswith('yzFace') or obj.material_slots[face.material_index].name.startswith('xzFace')  :
                Faces[j].update({'area_index':0})
            else :   
                print(face.material_index)
                Faces[j].update({'area_index':face.material_index})
            j+=1
        ## Areas information, dictionary with the 
        ## 5 values that compose an area data structure
        j=0
        Areas = {}
        for a in obj.area_list:
            Areas[j] = {}
            Areas[j].update({'area_index': a.area_index})
            Areas[j].update({'area_label': a.area_label})
            Areas[j].update({'area_gesture': a.area_gesture})
            Areas[j].update({'area_content':a.area_content})
            color = [0,0,0,0]
            color[0] = a.area_color[0]
            color[1] = a.area_color[1]
            color[2] = a.area_color[2]
            color[3] = a.area_color[3]
    
            Areas[j].update({'area_color':color})
            j+=1

        ## Storing all the materials to avoid problems for now
        j=0
        Materials = {}
        for mat in mesh.materials:
            Materials[j] = {}
            Materials[j].update({'name':mat.name})
            Materials[j].update({'diffuse':mat.diffuse_intensity})
            color = [0,0,0]
            color[0] = mat.diffuse_color[0]
            color[1] = mat.diffuse_color[1]
            color[2] = mat.diffuse_color[2]
            Materials[j].update({'color':color})
            j+=1
    

        
        

        ### Find the verts for xyz surfaces to store in the json file
        xz = []
        yz = []
        for polygon in mesh.polygons:
            mat = obj.material_slots[polygon.material_index].material.name
            if mat is not None:
                if mat.startswith("xzFace"):
                    verts_in_xzFace = polygon.vertices[:]
                    for vert in verts_in_xzFace:
                        xz.append(list(obj.data.vertices[vert].co))
                if mat.startswith("yzFace"):
                    verts_in_yzFace = polygon.vertices[:]
                    for vert in verts_in_yzFace:
                        yz.append(list(obj.data.vertices[vert].co))
        
        
        ## Storing data
        data['vertices'] = Vertices
        data['faces'] = Faces
        data['materials'] = Materials
        data['areas'] = Areas
        data['xz'] = xz
        data['yz'] = yz
        data['modelname'] = context.scene.inputName_model
        data['modeldescription'] = context.scene.inputIntroduction_model
        
        thread = threading.Thread(target= writeFile(fileName,data))
        thread.start()

        # wait here for the result to be available before continuing
        thread.join()
        with open(fileName + ".json") as json_file:
            dataprocess = json.load(json_file, object_pairs_hook=OrderedDict)

        blenderData = []
        xyz = []
        marked = []
        unmarked = []
        vertices = []
        areas = []
        generalinfo = []
        faceMap = {}
        pointMap = {}
        
        generalinfo.append("hello")
        generalinfo.append("test")
        
        xyz.append(data["xz"])
        xyz.append(data["yz"])
        
        blenderData.append(xyz)
        
        
        areas = [dataprocess['areas']]
        
        vertices = [dataprocess['vertices']]
        
        faces = dataprocess['faces']
        
        for f in faces:
            if faces[f]['area_index'] == 0:
                currentface = []
                currentvertices = []
                currentverticesindexes = []
                currentnormal = []
        
                for v in faces[f]['vertices']:
                    currentvertices.append(vertices[0][str(v)])
                    currentverticesindexes.append(str(v))
                for v in faces[f]['normal']:
                    currentnormal.append(v)
        
                faceMap[f] = currentverticesindexes
                currentface.append(currentvertices)
                currentface.append(currentnormal)
                currentface.append(f)
                unmarked.append(currentface)
            else:
                currentface = []
                generalinfo = []
                color = []
                currentvertices = []
                currentverticesindexes = []
                currentnormal = []
                areaindex = faces[f]['area_index'] - 1
                for v in faces[f]['vertices']:
                    currentverticesindexes.append(str(v))
                generalinfo.append(f)
        
                generalinfo.append(areas[0][str(areaindex)]['area_label'])
                generalinfo.append(areas[0][str(areaindex)]['area_content'])
                generalinfo.append(areas[0][str(areaindex)]['area_gesture'])
        
                color.append(areas[0][str(areaindex)]['area_color'])
        
                for v in faces[f]['vertices']:
                    currentvertices.append(vertices[0][str(v)])
                for v in faces[f]['normal']:
                    currentnormal.append(v)
                faceMap[f] = currentverticesindexes
                currentface.append(generalinfo)
        
        
                currentface.append(color[0])
                currentface.append(currentvertices)
                currentface.append(currentnormal)
                marked.append(currentface)
        
        blenderData.append(marked)
        blenderData.append(unmarked)
        blenderData.append(generalinfo)
        
        for faceIndex in iter(faceMap):
            for pointIndex in faceMap.get(faceIndex):
                if pointIndex not in pointMap:
                    pointMap[pointIndex] = set()
                pointMap.get(pointIndex).add(faceIndex)
        
        
        
        newdata = [blenderData, faceMap, pointMap]
            
        thread = threading.Thread(target= writeFilePickle(fileName,newdata))
        thread.start()

        # wait here for the result to be available before continuing
        thread.join()

        INPUTFILEADDRESS = fileName
        OUTPUTFILEADDRESS = fileName + "processed.json"
        
        modelData = blenderReader(INPUTFILEADDRESS)
        
        FaceDict={}
        index = 0
        tempcount = 0
        
        for eachFaceIndex in range(len(modelData.allFaces)):
            eachFace = modelData.allFaces[eachFaceIndex]
            templist = {}
            templist['marked'] = eachFace.marked
            if eachFace.marked:
                templist['index'] = eachFaceIndex
        
                templist['color'] = {"r":eachFace.blender_color[0],
                                  "g":eachFace.blender_color[1],
                                  "b": eachFace.blender_color[2]}
        
                tempcount = tempcount +1
            else:
                templist['index'] = eachFaceIndex
        
                templist['color'] = "null"
        
            if eachFace.label == "Body":
                eachFace.label = "m_body"
        
            if eachFace.label == "Jet engine":
                eachFace.label = "m_jet"
        
            if eachFace.label == "Cockpit":
                eachFace.label = "m_cockpit"
        
            if eachFace.label == "unmarked":
                eachFace.label = "nolabel"
                eachFace.content = "please activate an element with label"
        
            templist['label'] = eachFace.label
            templist['content'] = eachFace.content
            templist['normal'] = {"x":eachFace.normalConverted[0],
                                  "y":eachFace.normalConverted[1],
                                  "z": eachFace.normalConverted[2]}
            templist['verts'] = dict(vert1={'x': eachFace.vertsConverted[0][0],
                                            'y': eachFace.vertsConverted[0][1],
                                            'z': eachFace.vertsConverted[0][2]
                                            },
                                     vert2={'x': eachFace.vertsConverted[1][0],
                                            'y': eachFace.vertsConverted[1][1],
                                            'z': eachFace.vertsConverted[1][2]
                                                      },
                                     vert3={'x': eachFace.vertsConverted[2][0],
                                            'y': eachFace.vertsConverted[2][1],
                                            'z': eachFace.vertsConverted[2][2]
                                                                })
        
        
            tempIndexes = {}
            count = 0
            for eachNearFace in eachFace.relatedFaces:
                tempIndexes[str(count)] = eachNearFace
                count = count + 1
        
            templist['nearFaces'] = tempIndexes
            FaceDict['face'+str(index)]= templist
            index = index +1
        
        ExportData = {
            'modelName': modelData.generalInfo[0],
            'modelIntro' : modelData.generalInfo[1],
            'faces' : FaceDict
        }
        
        print(tempcount)
        
        with open(OUTPUTFILEADDRESS, 'w') as outfile:
            json.dump(ExportData, outfile)

        return {'FINISHED'}
    
###############################################################################################
####    MAGIC_import operator class                                    ########################
####    In this class we define the functions used to import the model #######################
####    module: Export and import                                      #####################
###############################################################################################

class MAGIC_import(bpy.types.Operator):
    bl_idname = "magic.import"
    bl_label = "import"

    def execute(self, context):
        
        ## SUPER SPECIAL NOTE ABOUT tracker scaffold, need to select the model after the scaffold, so materials store properly.
        ## Import file - Done
        with open(context.scene.import_path) as json_file:  
            data = json.load(json_file, object_pairs_hook=OrderedDict)
        
        ## Add each vertex to a list - Done
        Vertices = []
        i=0
        for p in data['vertices']:
            p = data['vertices'][str(i)]
            vector = mathutils.Vector((p))
            Vertices.append(vector)
            i+=1
        
        
        ## Add each face to a list - Done
        Faces = []
        i=0
        for f in data['faces']:
            f = data['faces'][str(i)]['vertices']
            Faces.append(f)
            i+=1
        
        ## Use file name to add the new mesh
        NewMesh = bpy.data.meshes.new("whatever")
        
        ### We define how the mesh will be built
        
        ## Use both lists to build the model
        NewMesh.from_pydata \
            (
                Vertices,
                [],
                Faces
            )
        NewMesh.update()
        
        context = bpy.context
        ## Use file name again to link it
        NewObj = bpy.data.objects.new("whatever", NewMesh)
        
        ### linking the new object to the scene
        context.scene.objects.link(NewObj)
        
        ### We select the object to add the materials to the face, and also the areas.
        context.scene.objects.active = NewObj
        
        ob = bpy.context.object 
                        
        current_mode = bpy.context.object.mode
        
        ### Check in which mode we are to handle errors
        if current_mode != 'EDIT' :
            bpy.ops.object.editmode_toggle()
        
        ### Object data
        mesh = ob.data
        
        ### Here we start adding the materials
        
        ##material = makeMaterial(name=p.name, diffuse=p.color, alpha=p.diffuse)
        ##mesh.materials.append(material)
        i=0
        for p in data['materials']:
            ## Change all of this to makeMaterial when doing in main component
            currentData = data['materials'][str(i)]
            material = makeMaterial(name=currentData['name'], diffuse=currentData['color'], alpha=currentData['diffuse'])
            mesh.materials.append(material)
            i+=1
            
        ### Here we start adding the areas
        i=0
        for p in data['areas']:
            currentData = data['areas'][str(i)]
            ob.area_list.add()
            ob.area_list[-1].area_index = currentData['area_index']
            ob.area_list[-1].area_label = currentData['area_label']
            ob.area_list[-1].area_content = currentData['area_content']
            ob.area_list[-1].area_gesture = currentData['area_gesture']
            ob.area_list[-1].area_color = currentData['area_color']
            i+=1
        
        ### Here we paint all the faces depending on their index    
        mesh = ob.data
        
        if bpy.context.object.mode != 'EDIT' :
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.remove_doubles(threshold=0.0001)
            
        bm = bmesh.from_edit_mesh(mesh)
        if hasattr(bm.faces, "ensure_lookup_table"): 
            bm.faces.ensure_lookup_table()
        
        ### We add the materials xzFace and yzFace to 2 specific faces in
        ### the scaffold to have a point of reference.
        i=0
        for f in data['faces']:
            area_index = data['faces'][str(i)]['area_index']
            bm.faces[i].material_index = area_index
            i+=1
            
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent(inside=False)
        
            
            
        bpy.ops.object.editmode_toggle()   

        return {'FINISHED'}


#
#   Registration
#   All panels and operators must be registered with Blender; otherwise
#   they do not show up. The simplest way to register everything in the
#   file is with a call to bpy.utils.register_module(__name__).
#
def register():
    bpy.utils.register_module(__name__)

### We define the different scene properties that will be used
### to create the panel of the tool and accept user inputs
### for exporting and labelling.

    bpy.types.Scene.inputName_model = bpy.props.StringProperty \
            (
            name="Model Name",
            description="Name for the model",
            default="Enter Name"
        )

    bpy.types.Scene.inputIntroduction_model = bpy.props.StringProperty \
            (
            name="Model Description",
            description="Introduction for the model",
            default="Enter Introduction"
        )

    bpy.types.Scene.inputLabel_hotarea = bpy.props.StringProperty \
            (
            name="Name",
            description="Label for selected areas",
            default="Enter Label"
        )

    bpy.types.Scene.inputContent_hotarea = bpy.props.StringProperty \
            (
            name="Description",
            description="Content for selected areas",
            default="Enter Content"
        )

    bpy.types.Scene.inputColor_hotarea = bpy.props.FloatVectorProperty(
        name="Color",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(0.75, 0.0, 0.8, 1.0)
    )

    bpy.types.Scene.inputGesture_hotarea = bpy.props.EnumProperty(
        items=[('Select', 'Select', "", 3),
               ('Point', 'Point', "", 2),
               ('Cancel', 'Cancel', "", 1)],
        name="Gesture")
    # bpy.types.DATA_PT_display.append(hndl_draw)

    bpy.types.Scene.export_path = bpy.props.StringProperty \
            (
            name="Output Directory",
            default="",
            description="Define the folder address to output the model",
            subtype='DIR_PATH'
        )
    bpy.types.Scene.import_path = bpy.props.StringProperty \
            (
            name="Import File",
            default="",
            description="Define the file address to import the model",
            subtype='FILE_PATH'
        )
    bpy.types.Scene.model_id = bpy.props.StringProperty \
            (
            name="Model ID",
            default="",
            description="Type in the model you want to load"
        )

    bpy.types.Scene.export_model = bpy.props.StringProperty \
            (
            name="STL directory",
            default="",
            description="Define the folder address of the destination",
            subtype='DIR_PATH'
        )
        
    bpy.types.Scene.export_model_file = bpy.props.StringProperty \
            (
            name="STL filename",
            default="",
            description="Define the name of your STL file",
            subtype='FILE_NAME'
        )

    bpy.types.Object.area_list = bpy.props.CollectionProperty(type=cls_AreaData)


def unregister():
    bpy.utils.unregister_module(__name__)
    del bpy.types.Scene.inputName_model
    del bpy.types.Scene.inputIntroduction_model
    del bpy.types.Scene.inputLabel_hotarea
    del bpy.types.Scene.inputContent_hotarea
    del bpy.types.Scene.inputColor_hotarea
    del bpy.types.Scene.inputGesture_hotarea
    del bpy.types.Scene.export_path
    del bpy.types.Scene.import_path
    del bpy.types.Scene.model_id
    del bpy.types.Object.area_list


if __name__ == "__main__":
    register()


