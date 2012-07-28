#!/usr/bin/env xmipp_python
#------------------------------------------------------------------------------------------------
# Xmipp protocol for projection matching
#
# Example use:
# ./xmipp_protocol_projmatch.py
#
# Authors: Roberto Marabini,
#          Sjors Scheres,    March 2008
#        Rewritten by Roberto Marabini 2012
#

import os
from os.path import join
from xmipp import MetaData, FileName, FILENAMENUMBERLENGTH, AGGR_COUNT,\
         MDL_CTF_MODEL, MDL_COUNT, MDL_RESOLUTION_FREQREAL, \
         MDL_RESOLUTION_FREQ, MDL_RESOLUTION_FRC, MDL_RESOLUTION_FRCRANDOMNOISE,\
         MDL_ANGLE_ROT, MDL_ANGLE_TILT, MDL_ANGLE_PSI, MDL_WEIGHT,\
         MDL_IMAGE, MDL_ORDER, MDL_REF, MDL_NEIGHBOR, MDValueEQ, MDL_REF3D,\
         MDL_SHIFT_X, MDL_SHIFT_Y, MDL_SHIFT_Z, Euler_angles2matrix,\
         MD_APPEND,MDL_DEFGROUP
         
    
from protlib_base import XmippProtocol, protocolMain
from protlib_utils import getListFromVector, getBoolListFromVector,\
     getComponentFromVector, runShowJ, runJob, createUniqueFileName
from protlib_sql import XmippProjectDb, SqliteDb
from config_protocols import protDict
from protlib_gui_ext import showWarning, showError
from protlib_gui_figure import XmippPlotter
from protlib_filesystem import linkAcquisitionInfoIfPresent\
                               , xmippExists\
                               , AcquisitionInfoExists\
                               , AcquisitionInfoGetSamplingRate
from math import radians

class ProtProjMatch(XmippProtocol):
#    def __init__(self, scriptname, workingdir, projectdir=None, logdir='Logs', restartStep=1, isIter=True):
    def __init__(self, scriptname, project=None):
                #XmippProtocol.__init__(self, protDict.ml2d.name, scriptname, project)

        XmippProtocol.__init__(self, protDict.projmatch.name, scriptname, project)
        self.CtfGroupDirectory = self.workingDirPath(self.CtfGroupDirectory)
        self.CtfGroupSubsetFileName = join(self.CtfGroupDirectory, self.CtfGroupSubsetFileName)
        self.DocFileWithOriginalAngles = self.workingDirPath(self.DocFileWithOriginalAngles)
        
        #maskedFileNamesIter = []# names masked volumes used as reference
#        self.createAuxTable = False
        self.NumberOfCtfGroups = 1
        
        self.ReferenceFileNames = self.ReferenceFileNames.split()
        self.numberOfReferences = len(self.ReferenceFileNames)

        self.Import = 'from protocol_projmatch_outside_loop import *;\
                       from protocol_projmatch_in_loop import *;' 
                #Convert directories/files  to absolute path from projdir
                
        # Now the CTF information and angles/shifts should come in images input file
        self.CTFDatName = self.DocFileName = ''
        
        #FIXME ROB
        if self.DoCtfCorrection:
            if self.SplitDefocusDocFile:
                self.CTFDatName = self.SplitDefocusDocFile
            else:
                self.CTFDatName = self.SelFileName
        
        if self.UseInitialAngles:
            self.DocFileName = self.SelFileName
        #sampling is now in acquisition info
        #self.ResolSam=float(self.ResolSam)
        self.ResolSam = AcquisitionInfoGetSamplingRate(self.SelFileName)
        
    def validate(self):
        from protlib_xmipp import validateInputSize
        errors = []
        
#        # Check reference and projection size match
#        _ReferenceFileNames = getListFromVector(self.ReferenceFileNames,processX=False)
#        _Parameters = {
#              'ReferenceFileNames':_ReferenceFileNames
#            , 'SelFileName':self.SelFileName
#            }

        # Check that all volumes have the same size
        #getListFromVector(self.ReferenceFileNames,processX=False)
        #listOfReferences=self.ReferenceFileNames.split()
        validateInputSize(self.ReferenceFileNames, self.SelFileName, errors)
            
        # Check options compatibility
        #if self.DoAlign2D and self.DoCtfCorrection:
        #    errors.append("Yyyou cannot realign classes AND perform CTF-correction. Switch either of them off!")

        # 3 Never allow DoAlign2D and DoCtfCorrection together
        if (int(getComponentFromVector(self.DoAlign2D, 1)) == 1 and self.DoCtfCorrection):
            errors.append("You cannot realign classes AND perform CTF-correction. Switch either of them off!")
    
        #4N outer radius is compulsory
        _OuterRadius = int(getComponentFromVector(self.OuterRadius, 1))
        _InnerRadius = int(getComponentFromVector(self.InnerRadius, 1))
        if _OuterRadius <= _InnerRadius:
            errors.append("OuterRadius must be larger than InnerRadius")

        #Check that acquisition info file is available
        if not AcquisitionInfoExists(self.SelFileName):
            errors.append("""Acquisition file for metadata %s is not available. 
Either import images before using them
or create a file named acquisition_info.xmd 
(see example below) and place it in the same directory than 
the %s file

EXAMPLE:
# XMIPP_STAR_1 *
# chage XXXXX by the sapling rate
data_
 _sampling_rate XXXXX
""" %(self.SelFileName,self.SelFileName))
            
        #FIXME ROB
        if self.DoCtfCorrection:
            tmpCTFDatName=''
            if self.SplitDefocusDocFile:
                tmpCTFDatName = self.SplitDefocusDocFile
            else:
                tmpCTFDatName = self.SelFileName
            tmpMd=MetaData(tmpCTFDatName)
            if not tmpMd.containsLabel(MDL_CTF_MODEL):
                errors.append("input file: " + tmpCTFDatName + " has no CTF information available")

            

        return errors 
    
    def summary(self):
        from protlib_sql import XmippProtocolDb
        super(ProtProjMatch, self).summary()
        
        
        file_name = join(self.CtfGroupDirectory, self.CtfGroupRootName) +'Info.xmd'
        if xmippExists(file_name):
            auxMD = MetaData("numberGroups@"+file_name)
            summaryNumberOfCtfGroups = auxMD.getValue(MDL_COUNT,auxMD.firstObject())
        else:
            summaryNumberOfCtfGroups = 1
            

        #self.ReferenceFileNames = getListFromVector(self.ReferenceFileNames)
        #self.ReferenceFileNames = self.ReferenceFileNames.split()

        #self.numberOfReferences = len(self.ReferenceFileNames)
        
        _dataBase  = XmippProtocolDb(self, self.scriptName, False)
        iteration = _dataBase.getRunIter()
        summary = ['Performed <%d/%d> iterations with angular sampling rate <%s>' 
                   % (iteration, self.NumberOfIterations, self.AngSamplingRateDeg)]
        filenames=(' '.join(self.ReferenceFileNames)).replace("'","")
        summary.append("Initial volume(s): [%s]"%filenames)
        summary.append("Input images: [%s]"%self.SelFileName)
        if (iteration > 1):
            ResolutionXmdCurrIterMaxSummary = self.getFilename('ResolutionXmdMax', iter=iteration, ref=1)
            ResolutionXmdCurrIterMaxSummary1 = self.getFilename('ResolutionXmdMax', iter=iteration-1, ref=1)
            if xmippExists(ResolutionXmdCurrIterMaxSummary):
                md = MetaData(ResolutionXmdCurrIterMaxSummary)
                id = md.firstObject()
                FourierMaxFrequencyOfInterestSummary = md.getValue(MDL_RESOLUTION_FREQREAL, id)
                summary += ['Resolution for first reference is <%s> A' % FourierMaxFrequencyOfInterestSummary]
            elif xmippExists(ResolutionXmdCurrIterMaxSummary1):
                md = MetaData(ResolutionXmdCurrIterMaxSummary1)
                id = md.firstObject()
                FourierMaxFrequencyOfInterestSummary = md.getValue(MDL_RESOLUTION_FREQREAL, id)
                summary += ['Resolution for first reference is <%s> A' % FourierMaxFrequencyOfInterestSummary]
            else:
                summary += ['<ERROR:> Resolution is not available but iteration number is not 1.\n <Something went wrong>. File=[%s] ' % ResolutionXmdCurrIterMaxSummary]            
        else:
            summary += ['Resolution is <%s>' % 'not available']            
        
        summary += ['Number of CTFgroups and References is <%d> and <%d> respectively'
                        % (summaryNumberOfCtfGroups, self.numberOfReferences)]

        return summary
    
    def visualize(self):
        
        plots = [k for k in ['DisplayReference'
                           , 'DisplayReconstruction'
                           , 'DisplayFilteredReconstruction'
                           , 'DisplayBFactorCorrectedVolume'
                           , 'DisplayProjectionMatchingLibrary'
                           , 'DisplayProjectionMatchingClasses'
                           , 'DisplayProjectionMatchingLibraryAndClasses'
                           , 'DisplayProjectionMatchingLibraryAndImages'
                           , 'DisplayDiscardedImages'
                           , 'DisplayAngularDistribution'
                           , 'DisplayResolutionPlots'] if self.ParamsDict[k]]
        if len(plots):
            self.launchProjmatchPlots(plots)

#    def visualizeReferences(self):
#        refs = self.getFilename('iter_refs')
#        if exists(refs):
#            blocks = getBlocksInMetaDataFile(refs)
#            lastBlock = blocks[-1]
#            try:
#                runShowJ("%(lastBlock)s@%(refs)s" % locals(), "512m", "--mode metadata --render")
#            except Exception, e:
#                from protlib_gui_ext import showError
#                showError("Error launching java app", str(e))
               
    def visualizeVar(self, varName):
#        if varName == 'DoShowReferences':
#            self.visualizeReferences()
#        else:
        self.launchProjmatchPlots([varName])
        
    def launchProjmatchPlots(self, selectedPlots):
        ''' Launch some plots for a Projection Matching protocol run '''
        import numpy as np
        _log = self.Log

        xplotter=None
        self._plot_count = 0
        
        def doPlot(plotName):
            return plotName in selectedPlots
        
        ref3Ds = map(int, getListFromVector(self.DisplayRef3DNo))
        iterations = map(int, getListFromVector(self.DisplayIterationsNo))
        
        if doPlot('DisplayReference'):
            VisualizationReferenceFileNames = [None] + self.ReferenceFileNames
            #print 'VisualizationReferenceFileNames: ',VisualizationReferenceFileNames
            for ref3d in ref3Ds:
                file_name = VisualizationReferenceFileNames[ref3d]
                #print 'ref3d: ',ref3d, ' | file_name:',file_name
                if xmippExists(file_name):
                    #Chimera
                    if(self.DisplayVolumeSlicesAlong == 'surface'):
                        parameters =  ' spider:' + file_name 
                        #print 'parameters: ',parameters
                        runJob(_log,
                               'chimera',
                               parameters
                               )
                    else:
                    #Xmipp_showj (x,y and z shows the same)
                        try:
                            runShowJ(file_name, extraParams = ' --dont_wrap ')
                        except Exception, e:
                            showError("Error launching java app", str(e))
                        
            
        if doPlot('DisplayReconstruction'):
            for ref3d in ref3Ds:
                for it in iterations:
                    file_name = self.getFilename('ReconstructedFileNamesIters', iter=it, ref=ref3d)
                    #print 'it: ',it, ' | file_name:',file_name
                    if xmippExists(file_name):
                        #Chimera
                        if(self.DisplayVolumeSlicesAlong == 'surface'):
                            parameters =  ' spider:' + file_name 
                            #print 'parameters: ',parameters
                            runJob(_log,
                                   'chimera',
                                   parameters
                                   )
                        else:
                        #Xmipp_showj (x,y and z shows the same)
                            try:
                                runShowJ(file_name, extraParams = ' --dont_wrap ')
                            except Exception, e:
                                showError("Error launching java app", str(e))
                            
        if doPlot('DisplayFilteredReconstruction'):
            for ref3d in ref3Ds:
                for it in iterations:
                    file_name = self.getFilename('ReconstructedFilteredFileNamesIters', iter=it, ref=ref3d)
                    #print 'it: ',it, ' | file_name:',file_name
                    if xmippExists(file_name):
                                                #Chimera
                        if(self.DisplayVolumeSlicesAlong == 'surface'):
                            parameters =  ' spider:' + file_name 
                            #print 'parameters: ',parameters
                            runJob(_log,
                                   'chimera',
                                   parameters
                                   )
                        else:
                        #Xmipp_showj (x,y and z shows the same)

                            try:
                                runShowJ(file_name, extraParams = ' --dont_wrap ')
                            except Exception, e:
                                showError("Error launching java app", str(e))
                
        if doPlot('DisplayBFactorCorrectedVolume'):
            #if(self.DisplayVolumeSlicesAlong == 'surface'):
            
            for ref3d in ref3Ds:
                for it in iterations:
                    file_name = self.getFilename('ReconstructedFileNamesIters', iter=it, ref=ref3d)
                    file_name_bfactor = file_name + '.bfactor'
                    
                    parameters = ' -i ' + file_name + \
                        ' --sampling ' + str(self.ResolSam) + \
                        ' --maxres ' + str(self.MaxRes) + \
                        ' -o ' + file_name_bfactor
                        
                    parameters +=  ' ' + self.CorrectBfactorExtraCommand
                    
                    runJob(_log,
                           'xmipp_volume_correct_bfactor',
                           parameters
                           )

                    if xmippExists(file_name_bfactor):
                        
                                                                        #Chimera
                        if(self.DisplayVolumeSlicesAlong == 'surface'):
                            parameters =  ' spider:' + file_name_bfactor 
                            #print 'parameters: ',parameters
                            runJob(_log,
                                   'chimera',
                                   parameters
                                   )
                        else:
                        #Xmipp_showj (x,y and z shows the same)

                            try:
                                runShowJ(file_name_bfactor, extraParams = ' --dont_wrap ')
                            except Exception, e:
                                showError("Error launching java app", str(e))


        if doPlot('DisplayProjectionMatchingLibrary'):
        #map stack position with ref number
            MDin  = MetaData()
            MDout = MetaData()
            for ref3d in ref3Ds:
                for it in iterations:
                    convert_refno_to_stack_position={}
                    file_nameReferences = 'projectionDirections@'+self.getFilename('ProjectLibrarySampling', iter=it, ref=ref3d)
                    #last reference name
                    mdReferences     = MetaData(file_nameReferences)
                    mdReferencesSize = mdReferences.size()
                    for id in mdReferences:
                        convert_refno_to_stack_position[mdReferences.getValue(MDL_NEIGHBOR,id)]=id
                    file_nameAverages   = self.getFilename('OutClassesXmd', iter=it, ref=ref3d)
                    if xmippExists(file_nameAverages):
                        #print "OutClassesXmd", OutClassesXmd
                        MDin.read(file_nameAverages)
                        MDout.clear()
                        for i in MDin:
                            #id1=MDout.addObject()
                            #MDout.setValue(MDL_IMAGE,MDin.getValue(MDL_IMAGE,i),id1)
                            ref2D = MDin.getValue(MDL_REF,i)
                            file_references = self.getFilename('ProjectLibraryStk', iter=it, ref=ref3d)
                            file_reference=FileName()
                            file_reference.compose(convert_refno_to_stack_position[ref2D],file_references)
                            id2=MDout.addObject()
                            MDout.setValue(MDL_IMAGE,file_reference,id2)
                        if MDout.size()==0:
                            print "Empty metadata: ", file_name
                        else:
                            try:
                                file_nameReferences = self.getFilename('ProjectLibrarySampling', iter=it, ref=ref3d)
                                sfn   = createUniqueFileName(file_nameReferences)
                                file_nameReferences = 'projectionDirections@'+sfn
                                MDout.write( sfn )
                                runShowJ(sfn, extraParams = ' --dont_wrap ')
                            except Exception, e:
                                showError("Error launching java app", str(e))

        if doPlot('DisplayProjectionMatchingClasses'):
            MD = MetaData()
            for ref3d in ref3Ds:
                for it in iterations:
                    file_name = self.getFilename('OutClassesXmd', iter=it, ref=ref3d)
                    if xmippExists(file_name):
                        MD.read(file_name)
                        if MD.size()==0:
                            print "Empty metadata: ", file_name
                        else:
                            try:
                                runShowJ(file_name,extraParams = ' --dont_wrap ')
                            except Exception, e:
                                showError("Error launching java app", str(e))
        
        if doPlot('DisplayProjectionMatchingLibraryAndClasses'):       
        #map stack position with ref number
            MDin  = MetaData()
            MDout = MetaData()
            for ref3d in ref3Ds:
                for it in iterations:
                    convert_refno_to_stack_position={}
                    file_nameReferences = 'projectionDirections@'+self.getFilename('ProjectLibrarySampling', iter=it, ref=ref3d)
                    #last reference name
                    mdReferences     = MetaData(file_nameReferences)
                    mdReferencesSize = mdReferences.size()
                    for id in mdReferences:
                        convert_refno_to_stack_position[mdReferences.getValue(MDL_NEIGHBOR,id)]=id
                    file_nameAverages   = self.getFilename('OutClassesXmd', iter=it, ref=ref3d)
                    if xmippExists(file_nameAverages):
                        #print "OutClassesXmd", OutClassesXmd
                        MDin.read(file_nameAverages)
                        MDout.clear()
                        for i in MDin:
                            id1=MDout.addObject()
                            MDout.setValue(MDL_IMAGE,     MDin.getValue(MDL_IMAGE,i),id1)
                            #MDout.setValue(MDL_SHIFT_X, MDin.getValue(MDL_SHIFT_X,i),id1)
                            #MDout.setValue(MDL_SHIFT_Y, MDin.getValue(MDL_SHIFT_Y,i),id1)
                            #MDout.setValue(MDL_SHIFT_Z, MDin.getValue(MDL_SHIFT_Z,i),id1)
                            ref2D = MDin.getValue(MDL_REF,i)
                            file_references = self.getFilename('ProjectLibraryStk', iter=it, ref=ref3d)
                            file_reference=FileName()
                            file_reference.compose(convert_refno_to_stack_position[ref2D],file_references)
                            id2=MDout.addObject()
                            MDout.setValue(MDL_IMAGE,file_reference,id2)
                            #MDout.setValue(MDL_SHIFT_X,   0.,id1)
                            #MDout.setValue(MDL_SHIFT_Y,   0.,id1)
                            #MDout.setValue(MDL_SHIFT_Z,   0.,id1)
                        if MDout.size()==0:
                            print "Empty metadata: ", file_name
                        else:
                            try:
                                file_nameReferences = self.getFilename('ProjectLibrarySampling', iter=it, ref=ref3d)
                                sfn   = createUniqueFileName(file_nameReferences)
                                file_nameReferences = 'projectionDirections@'+sfn
                                MDout.write( sfn )
                                runShowJ(sfn, extraParams = ' --dont_wrap ')
                            except Exception, e:
                                showError("Error launching java app", str(e))

        if doPlot('DisplayProjectionMatchingLibraryAndImages'):
            from numpy  import array, dot
        #map stack position with ref number
            MDin  = MetaData()
            MDout = MetaData()
            MDtmp = MetaData()
            for ref3d in ref3Ds:
                for it in iterations:
                    convert_refno_to_stack_position={}
                    file_nameReferences = 'projectionDirections@'+self.getFilename('ProjectLibrarySampling', iter=it, ref=ref3d)
                    #last reference name
                    mdReferences     = MetaData(file_nameReferences)
                    mdReferencesSize = mdReferences.size()
                    for id in mdReferences:
                        convert_refno_to_stack_position[mdReferences.getValue(MDL_NEIGHBOR,id)]=id
                    file_nameImages = self.getFilename('DocfileInputAnglesIters', iter=it)
                    if xmippExists(file_nameImages):
                        #print "OutClassesXmd", OutClassesXmd
                        MDtmp.read(file_nameImages)#query with ref3D
                        MDin.importObjects(MDtmp, MDValueEQ(MDL_REF3D, ref3d))
                        MDout.clear()
                        for i in MDin:
                            id1=MDout.addObject()
                            MDout.setValue(MDL_IMAGE,MDin.getValue(MDL_IMAGE,i),id1)
#                            MDout.setValue(MDL_ANGLE_ROT, MDin.getValue(MDL_ANGLE_ROT,i),id1)
#                            MDout.setValue(MDL_ANGLE_TILT,MDin.getValue(MDL_ANGLE_TILT,i),id1)
                            psi =-1.*MDin.getValue(MDL_ANGLE_PSI,i)
                            eulerMatrix = Euler_angles2matrix(0.,0.,psi)
                            x = MDin.getValue(MDL_SHIFT_X,i)
                            y = MDin.getValue(MDL_SHIFT_Y,i)
                            
                            shift       = array([x, y, 0])
                            shiftOut    = dot(eulerMatrix, shift)
                            [x,y,z]= shiftOut
                            MDout.setValue(MDL_ANGLE_PSI, psi,id1)
                            MDout.setValue(MDL_SHIFT_X, x,id1)
                            MDout.setValue(MDL_SHIFT_Y, y,id1)
                            
                            ref2D = MDin.getValue(MDL_REF,i)
                            file_references = self.getFilename('ProjectLibraryStk', iter=it, ref=ref3d)
                            file_reference=FileName()
                            file_reference.compose(convert_refno_to_stack_position[ref2D],file_references)
                            id2=MDout.addObject()
                            MDout.setValue(MDL_IMAGE,file_reference,id2)
#                            MDout.setValue(MDL_ANGLE_ROT,0.,id2)
#                            MDout.setValue(MDL_ANGLE_TILT,0.,id2)
                            MDout.setValue(MDL_ANGLE_PSI,0.,id2)
#                            MDout.setValue(MDL_SHIFT_X,   0.,id1)
#                            MDout.setValue(MDL_SHIFT_Y,   0.,id1)

                        if MDout.size()==0:
                            print "Empty metadata: ", file_name
                        else:
                            try:
                                file_nameReferences = self.getFilename('ProjectLibrarySampling', iter=it, ref=ref3d)
                                sfn   = createUniqueFileName(file_nameReferences)
                                file_nameReferences = 'projectionDirections@'+sfn
                                MDout.write( sfn )
                                runShowJ(sfn, extraParams = ' --dont_wrap ')
                            except Exception, e:
                                showError("Error launching java app", str(e))

            
        if doPlot('DisplayDiscardedImages'):
            MD = MetaData()
            for it in iterations:
                file_name = self.getFilename('OutClassesDiscarded', iter=it)
                #print 'it: ',it, ' | file_name:',file_name
                if xmippExists(file_name):
                    MD.read(file_name)
                    if MD.size()==0:
                        print "Empty metadata: ", file_name
                    else:
                        try:
                            runShowJ(file_name, extraParams = ' --dont_wrap ')
                        except Exception, e:
                            showError("Error launching java app", str(e))
            
        if doPlot('DisplayAngularDistribution'):
            if(self.DisplayAngularDistributionWith == '3D'):
                for ref3d in ref3Ds:
                    for it in iterations:
                        _OuterRadius = getComponentFromVector(self.OuterRadius, it)
                        _InnerRadius = getComponentFromVector(self.InnerRadius, it)

                        file_name = self.getFilename('OutClassesXmd', iter=it, ref=ref3d)
                        file_name_bild = file_name + '.bild'
    
                        parameters =  ' -i ' + file_name + \
                            ' -o ' + file_name_bild + \
                            ' chimera ' + str(float(_OuterRadius) * 1.1)
                            
                        runJob(_log,
                               'xmipp_angular_distribution_show',
                               parameters
                               )
                        
                        file_name_rec_filt = self.getFilename('ReconstructedFilteredFileNamesIters', iter=it, ref=ref3d)
                        
                        parameters =  ' ' + file_name_bild + ' spider:' + file_name_rec_filt 
                            
                        runJob(_log,
                               'chimera',
                               parameters
                               )
            else: #DisplayAngularDistributionWith == '2D'
                for it in iterations:
                    if(len(ref3Ds) == 1):
                        gridsize1 = [1, 1]
                    elif (len(ref3Ds) == 2):
                        gridsize1 = [2, 1]
                    else:
                        gridsize1 = [(len(ref3Ds)+1)/2, 2]
                    
                    xplotter = XmippPlotter(*gridsize1, mainTitle='Iteration_%d' % it, windowTitle="AngularDistribution")
                    
                    for ref3d in ref3Ds:
                        file_name = self.getFilename('OutClassesXmd', iter=it, ref=ref3d)
                        md = MetaData(file_name)
                        plot_title = 'Ref3D_%d' % ref3d
                        xplotter.plotAngularDistribution(plot_title, md)
                    xplotter.draw()
                    
        if doPlot('DisplayResolutionPlots'):
            if(len(ref3Ds) == 1):
                gridsize1 = [1, 1]
            elif (len(ref3Ds) == 2):
                gridsize1 = [2, 1]
            else:
                gridsize1 = [(len(ref3Ds)+1)/2, 2]
            xplotter = XmippPlotter(*gridsize1,windowTitle="ResolutionFSC")
            #print 'gridsize1: ', gridsize1
            #print 'iterations: ', iterations
            #print 'ref3Ds: ', ref3Ds
            
            for ref3d in ref3Ds:
                plot_title = 'Ref3D_%s' % ref3d
                a = xplotter.createSubPlot(plot_title, 'Armstrongs^-1', 'Fourier Shell Correlation', yformat=False)
                legendName=[]
                for it in iterations:
                    file_name = self.getFilename('ResolutionXmdFile', iter=it, ref=ref3d)
                    #print 'it: ',it, ' | file_name:',file_name
                    md = MetaData(file_name)
                    resolution_inv = [md.getValue(MDL_RESOLUTION_FREQ, id) for id in md]
                    frc = [md.getValue(MDL_RESOLUTION_FRC, id) for id in md]
                    a.plot(resolution_inv, frc)
                    legendName.append('Iter_'+str(it))
                xplotter.showLegend(legendName)
                
                if (self.ResolutionThreshold < max(frc)):
                    a.plot([min(resolution_inv), max(resolution_inv)], [self.ResolutionThreshold, self.ResolutionThreshold], color='black', linestyle='--')
            
            xplotter.draw()
    
        if xplotter:
            xplotter.show()
    
#    def createAcquisitionData(_log,samplingRate,fnOut):
#        mdAcquisition = xmipp.MetaData()
#        mdAcquisition.setValue(xmipp.MDL_SAMPLINGRATE,samplingRate,mdAcquisition.addObject())
#        mdAcquisition.write(fnOut)


    
    def createFilenameTemplates(self):  
        #Some class variables
        LibraryDir = "ReferenceLibrary"
        extraParams = {'ReferenceVolumeName': 'reference_volume.vol',
        'LibraryDir': LibraryDir,
        'ProjectLibraryRootName': join(LibraryDir, "gallery"),
        'ProjMatchDir': "ProjMatchClasses",
        'ProjMatchName': self.Name,
        'ClassAverageName': 'class_average',
        #ProjMatchRootName = ProjMatchDir + "/" + ProjMatchName
        'ForReconstructionSel': "reconstruction.sel",
        'ForReconstructionDoc': "reconstruction.doc",
        'MultiAlign2dSel': "multi_align2d.sel",
        'BlockWithAllExpImages' : 'all_exp_images',
        'DocFileWithOriginalAngles': 'original_angles.doc',
        'Docfile_with_current_angles': 'current_angles',
        'Docfile_with_final_results': 'results.xmd',
        'FilteredReconstruction': "filtered_reconstruction",
        'ReconstructedVolume': "reconstruction",
        'MaskReferenceVolume': "masked_reference",
        'OutputFsc': "resolution.fsc",
        'CtfGroupDirectory': "CtfGroups",
        'CtfGroupRootName': "ctf",
        'CtfGroupSubsetFileName': "ctf_images.sel"
        }
        self.ParamsDict.update(extraParams)
        # Set as protocol variables
        for k, v in extraParams.iteritems():
            setattr(self, k, v)
                              
        Iter = 'Iter_%(iter)03d'
        Ref3D = 'Ref3D_%(ref)03d'
        Ctf = 'CtfGroup_%(ctf)06d'
        IterDir = self.workingDirPath(Iter)
        
        #ProjMatchDirs = join(IterDir, '%(ProjMatchDir)s.doc')
        ProjMatchDirs = join(IterDir, '%(ProjMatchDir)s')
        _OutClassesXmd = join(ProjMatchDirs, '%(ProjMatchName)s_' + Ref3D + '.xmd')
        _OutClassesXmdS1 = join(ProjMatchDirs, '%(ProjMatchName)s_split_1_' + Ref3D + '.xmd')
        _OutClassesXmdS2 = join(ProjMatchDirs, '%(ProjMatchName)s_split_2_' + Ref3D + '.xmd')
        CtfGroupBase = join(self.workingDirPath(), self.CtfGroupDirectory, '%(CtfGroupRootName)s')
        ProjLibRootNames = join(IterDir, '%(ProjectLibraryRootName)s_' + Ref3D)
        return {
                # Global filenames templates
                'IterDir': IterDir,
                'ProjMatchDirs': ProjMatchDirs,
                'DocfileInputAnglesIters': join(IterDir, '%(Docfile_with_current_angles)s.doc'),
                'LibraryDirs': join(IterDir, '%(LibraryDir)s'),
                'ProjectLibraryRootNames': ProjLibRootNames,
                'ProjMatchRootNames': join(ProjMatchDirs, '%(ProjMatchName)s_' + Ref3D + '.doc'),
                'ProjMatchRootNamesWithoutRef': join(ProjMatchDirs, '%(ProjMatchName)s.doc'),
                'OutClasses': join(ProjMatchDirs, '%(ProjMatchName)s'),
                'OutClassesXmd': _OutClassesXmd,
                'OutClassesStk': join(ProjMatchDirs, '%(ProjMatchName)s_' + Ref3D + '.stk'),
                'OutClassesDiscarded': join(ProjMatchDirs, '%(ProjMatchName)s_discarded.xmd'),
                'ReconstructionXmd': Ref3D + '@' +_OutClassesXmd,
                'ReconstructionXmdSplit1': Ref3D + '@' +_OutClassesXmdS1,
                'ReconstructionXmdSplit2': Ref3D + '@' +_OutClassesXmdS2,
                'MaskedFileNamesIters': join(IterDir, '%(MaskReferenceVolume)s_' + Ref3D + '.vol'),
                'ReconstructedFileNamesIters': join(IterDir, '%(ReconstructedVolume)s_' + Ref3D + '.vol'),
                'ReconstructedFileNamesItersSplit1': join(IterDir, '%(ReconstructedVolume)s_split_1_' + Ref3D + '.vol'),
                'ReconstructedFileNamesItersSplit2': join(IterDir, '%(ReconstructedVolume)s_split_2_' + Ref3D + '.vol'),
                'ReconstructedFilteredFileNamesIters': join(IterDir, '%(ReconstructedVolume)s_filtered_' + Ref3D + '.vol'),
                'ResolutionXmdFile': join(IterDir, '%(ReconstructedVolume)s_' + Ref3D + '_frc.xmd'),
                'ResolutionXmd': 'resolution@' + join(IterDir, '%(ReconstructedVolume)s_' + Ref3D + '_frc.xmd'),
                'ResolutionXmdMax': 'resolution_max@' + join(IterDir, '%(ReconstructedVolume)s_' + Ref3D + '_frc.xmd'),
                'MaskedFileNamesIters': join(IterDir, '%(MaskReferenceVolume)s_' + Ref3D + '.vol'),
                # Particular templates for executeCtfGroups  
                'ImageCTFpairs': CtfGroupBase + '_images.sel',
                'CTFGroupSummary': CtfGroupBase + 'Info.xmd',
                'StackCTFs': CtfGroupBase + '_ctf.stk',
                'StackWienerFilters': CtfGroupBase + '_wien.stk',
                'SplitAtDefocus': CtfGroupBase + '_split.doc',
                # Particular templates for angular_project_library 
                'ProjectLibraryStk': ProjLibRootNames + '.stk',
                'ProjectLibraryDoc': ProjLibRootNames + '.doc',
                'ProjectLibrarySampling': ProjLibRootNames + '_sampling.xmd',
                'ProjectLibraryGroupSampling': ProjLibRootNames + '_group%(group)06d_sampling.xmd',
                }
         
    
    def preRun(self):
        
        _dataBase = self.Db
        
#        fnOut=self.workingDirPath("acquisition_info.xmd")
#        _dataBase.insertStep('createAcquisitionData',verifyfiles=[fnOut],samplingRate=self.AngSamplingRateDeg, fnOut=fnOut)
#        print "createAcquisitionData|| fnOut=",fnOut, " samplingRate=", self.AngSamplingRateDeg

        _dataBase.insertStep("linkAcquisitionInfoIfPresent",
                        InputFile=self.SelFileName,
                        dirDest=self.WorkingDir)
        
        # Construct special filename list with zero special case
        self.DocFileInputAngles = [self.DocFileWithOriginalAngles] + [self.getFilename('DocfileInputAnglesIters', iter=i) for i in range(1, self.NumberOfIterations + 1)]
        #print 'self.DocFileInputAngles: ', self.DocFileInputAngles
        self.reconstructedFileNamesIters = [[None] + self.ReferenceFileNames]
        for iterN in range(1, self.NumberOfIterations + 1):
            self.reconstructedFileNamesIters.append([None] + [self.getFilename('ReconstructedFileNamesIters', iter=iterN, ref=r) for r in range(1, self.numberOfReferences + 1)])

        self.reconstructedFilteredFileNamesIters = [[None] + self.ReferenceFileNames]
        for iterN in range(1, self.NumberOfIterations + 1):
            self.reconstructedFilteredFileNamesIters.append([None] + [self.getFilename('ReconstructedFilteredFileNamesIters', iter=iterN, ref=r) for r in range(1, self.numberOfReferences + 1)])

        _tmp = self.FourierMaxFrequencyOfInterest
        self.FourierMaxFrequencyOfInterest = list(-1 for  k in range(0, self.NumberOfIterations + 1 +1))
        self.FourierMaxFrequencyOfInterest[1] = _tmp
        #parameter for projection matching
        self.Align2DIterNr = [-1] + getListFromVector(self.Align2DIterNr, self.NumberOfIterations)
        self.Align2dMaxChangeOffset = [-1] + getListFromVector(self.Align2dMaxChangeOffset, self.NumberOfIterations)
        self.Align2dMaxChangeRot = [-1] + getListFromVector(self.Align2dMaxChangeRot, self.NumberOfIterations)
        self.AngSamplingRateDeg = [-1] + getListFromVector(self.AngSamplingRateDeg, self.NumberOfIterations)
        self.ConstantToAddToFiltration = [-1] + getListFromVector(self.ConstantToAddToFiltration, self.NumberOfIterations)
        self.ConstantToAddToMaxReconstructionFrequency = [-1] + getListFromVector(self.ConstantToAddToMaxReconstructionFrequency, self.NumberOfIterations)
        self.DiscardPercentage = [-1] + getListFromVector(self.DiscardPercentage, self.NumberOfIterations)
        self.DiscardPercentagePerClass = [-1] + getListFromVector(self.DiscardPercentagePerClass, self.NumberOfIterations)
        self.DoAlign2D = [False] + getBoolListFromVector(self.DoAlign2D, self.NumberOfIterations)
        self.DoComputeResolution = [False] + getBoolListFromVector(self.DoComputeResolution, self.NumberOfIterations)
        self.DoSplitReferenceImages = [False] + getBoolListFromVector(self.DoSplitReferenceImages, self.NumberOfIterations)
        self.InnerRadius = [False] + getListFromVector(self.InnerRadius, self.NumberOfIterations)
        self.MaxChangeInAngles = [-1] + getListFromVector(self.MaxChangeInAngles, self.NumberOfIterations)
        self.MaxChangeOffset = [-1] + getListFromVector(self.MaxChangeOffset, self.NumberOfIterations)
        self.MinimumCrossCorrelation = [-1] + getListFromVector(self.MinimumCrossCorrelation, self.NumberOfIterations)
        self.OnlyWinner = [False] + getBoolListFromVector(self.OnlyWinner, self.NumberOfIterations)
        self.OuterRadius = [False] + getListFromVector(self.OuterRadius, self.NumberOfIterations)
        self.PerturbProjectionDirections = [False] + getBoolListFromVector(self.PerturbProjectionDirections, self.NumberOfIterations)
        self.ReferenceIsCtfCorrected = [-1] + getListFromVector(str(self.ReferenceIsCtfCorrected) + " True", self.NumberOfIterations)
        self.ScaleNumberOfSteps = [-1] + getListFromVector(self.ScaleNumberOfSteps, self.NumberOfIterations)
        self.ScaleStep = [-1] + getListFromVector(self.ScaleStep, self.NumberOfIterations)
        self.Search5DShift = [-1] + getListFromVector(self.Search5DShift, self.NumberOfIterations)
        self.Search5DStep = [-1] + getListFromVector(self.Search5DStep, self.NumberOfIterations)
        self.SymmetryGroup = [-1] + getListFromVector(self.SymmetryGroup, self.NumberOfIterations)
        
#        self.ProjectionMethod=ProjectionMethod
#        self.PaddingAngularProjection=PaddingAngularProjection
#        self.KernelAngularProjection=KernelAngularProjection
        
        
    def otherActionsToBePerformedBeforeLoop(self):
        #print "in otherActionsToBePerformedBeforeLoop"
        _VerifyFiles = []

        _dataBase = self.Db
        
        file_name = join(self.CtfGroupDirectory, self.CtfGroupRootName) +'Info.xmd'
        if xmippExists(file_name):
            auxMD = MetaData("numberGroups@"+file_name)
            self.NumberOfCtfGroups = auxMD.getValue(MDL_COUNT,auxMD.firstObject())
        else:
            self.NumberOfCtfGroups = 1

        #create dir for iteration 1 (This need to be 0 or 1? ROB FIXME
        #!a _dataBase.insertStep('createDir', path = self.getIterDirName(0))
    
        #7 make CTF groups
        verifyFiles = [self.getFilename('ImageCTFpairs')]
        if self.DoCtfCorrection:
            verifyFiles += [self.getFilename(k) \
                            for k in ['CTFGroupSummary',
                                      'StackCTFs',
                                      'StackWienerFilters',
                                      'SplitAtDefocus']]

        _dataBase.insertStep('executeCtfGroups', verifyfiles=verifyFiles
                                               , CTFDatName=self.CTFDatName
                                               , CtfGroupDirectory=self.CtfGroupDirectory
                                               , CtfGroupMaxDiff=self.CtfGroupMaxDiff
                                               , CtfGroupMaxResol=self.CtfGroupMaxResol
                                               , CtfGroupRootName=self.CtfGroupRootName
                                               , DataArePhaseFlipped=self.DataArePhaseFlipped
                                               , DoAutoCtfGroup=self.DoAutoCtfGroup
                                               , DoCtfCorrection=self.DoCtfCorrection
                                               , PaddingFactor=self.PaddingFactor
                                               , SamplingRate=self.ResolSam
                                               , SelFileName=self.SelFileName
                                               , SplitDefocusDocFile=self.SplitDefocusDocFile
                                               , WienerConstant=self.WienerConstant)
        #Create Initial angular file. Either fill it with zeros or copy input
        _dataBase.insertStep('initAngularReferenceFile', verifyfiles=[self.DocFileWithOriginalAngles]
                                                                , BlockWithAllExpImages = self.BlockWithAllExpImages
                                                                , CtfGroupDirectory=self.CtfGroupDirectory
                                                                , CtfGroupRootName=self.CtfGroupRootName
                                                                , DocFileName=self.DocFileName
                                                                , DocFileWithOriginalAngles=self.DocFileWithOriginalAngles
                                                                , SelFileName=self.SelFileName)
    
        #Save all parameters in dict for future runs (this is done by database)
        #so far no parameter is being saved, but dummy=0
        #self.Db.setIteration(XmippProjectDb.doAlways)
        #_dataBase.insertStep('self.saveParameters', SystemFlavour = self.SystemFlavour)
        #_dataBase.insertStep('self.loadParameters', None, None)
        #self.Db.setIteration(1)
        #no entries will be save untill this commit
        #print "commit databse"
        _dataBase.connection.commit()
    
    def getIterDirName(self, iterN):
        return join(self.projectDir, self.WorkingDir, 'Iter_%02d' % iterN)
    
    def actionsToBePerformedInsideLoop(self):
        _log = self.Log
        _dataBase = self.Db

        for iterN in range(1, self.NumberOfIterations + 1):
            _dataBase.setIteration(iterN)
            # create IterationDir
            _dataBase.insertStep('createDir', path=self.getFilename('IterDir', iter=iterN))
    
            #Create directory with classes
            _dataBase.insertStep('createDir', path=self.getFilename('ProjMatchDirs', iter=iterN))
        
            #Create directory with image libraries
            id = _dataBase.insertStep('createDir', path=self.getFilename('LibraryDirs', iter=iterN))

            ProjMatchRootNameList = ['']
            for refN in range(1, self.numberOfReferences + 1):
                # Mask reference volume
                maskedFileName = self.getFilename('MaskedFileNamesIters', iter=iterN, ref=refN)
                _dataBase.insertStep('executeMask'
                                    , verifyfiles=[maskedFileName]
                                    , parent_step_id=id
                                    , DoMask=self.DoMask
                                    , DoSphericalMask=self.DoSphericalMask
                                    , maskedFileName=maskedFileName
                                    , maskRadius=self.MaskRadius
                                    , ReconstructedFilteredVolume = self.reconstructedFilteredFileNamesIters[iterN-1][refN]
                                    , userSuppliedMask=self.MaskFileName)

                # angular_project_library
                #file with projections
                auxFn = self.getFilename('ProjectLibraryRootNames', iter=iterN, ref=refN)
                #file with sampling point neighbourhood for each ctf group, this is reduntant but useful
                #Files: projections, projection_angles, sampling_points and neighbourhood
                _VerifyFiles = [self.getFilename('ProjectLibrary' + e, iter=iterN, ref=refN)
                                     for e in ['Stk', 'Doc', 'Sampling']]
                #Ask only for first and last, if we ask for all ctfgroup files the sql command max lenght is reached
                _VerifyFiles = _VerifyFiles + [self.getFilename('ProjectLibraryGroupSampling', iter=iterN, ref=refN, group=g) \
                                     for g in range (1, self.NumberOfCtfGroups+1)]
                projLibFn =  self.getFilename('ProjectLibraryStk', iter=iterN, ref=refN)  
                   

      
                _dataBase.insertStep('angular_project_library', verifyfiles=_VerifyFiles
                                    , AngSamplingRateDeg=self.AngSamplingRateDeg[iterN]
                                    , BlockWithAllExpImages = self.BlockWithAllExpImages
                                    , ConstantToAddToFiltration = self.ConstantToAddToFiltration[iterN]
                                    , CtfGroupSubsetFileName=self.CtfGroupSubsetFileName
                                    , DoCtfCorrection=self.DoCtfCorrection
                                    , DocFileInputAngles=self.DocFileInputAngles[iterN - 1]
                                    , DoParallel=self.DoParallel
                                    , DoRestricSearchbyTiltAngle=self.DoRestricSearchbyTiltAngle
                                    , FourierMaxFrequencyOfInterest = self.FourierMaxFrequencyOfInterest[iterN]
                                    , KernelAngularProjection=self.KernelAngularProjection
                                    , MaxChangeInAngles=self.MaxChangeInAngles[iterN]
                                    , maskedFileNamesIter=maskedFileName
                                    , MpiJobSize=self.MpiJobSize
                                    , NumberOfMpi=self.NumberOfMpi
                                    , NumberOfThreads=self.NumberOfThreads
                                    , OnlyWinner=self.OnlyWinner[iterN]
                                    , PaddingAngularProjection=self.PaddingAngularProjection
                                    , PerturbProjectionDirections=self.PerturbProjectionDirections[iterN]
                                    , ProjectLibraryRootName=projLibFn
                                    , ProjectionMethod=self.ProjectionMethod
                                    , ResolSam = self.ResolSam
                                    , ResolutionXmdPrevIterMax = self.getFilename('ResolutionXmdMax', iter=iterN-1, ref=refN)
                                    , SymmetryGroup=self.SymmetryGroup[iterN]
                                    , SymmetryGroupNeighbourhood=self.SymmetryGroupNeighbourhood
                                    , Tilt0=self.Tilt0
                                    , TiltF=self.TiltF)
                # projectionMatching    
                #File with list of images and references
                ProjMatchRootName = self.getFilename('ProjMatchRootNames', iter=iterN, ref=refN)
                ProjMatchRootNameList.append(ProjMatchRootName)
#                for i in range (1, self.NumberOfCtfGroups + 1):
#                    _VerifyFiles.append(auxFn + "_group" + str(i).zfill(6) + "_sampling.xmd")
                    
                _dataBase.insertStep('projection_matching', verifyfiles=[ProjMatchRootName],
                                      AvailableMemory=self.AvailableMemory
                                    , CtfGroupRootName=self.CtfGroupRootName
                                    , CtfGroupDirectory=self.CtfGroupDirectory
                                    , DocFileInputAngles=self.DocFileInputAngles[iterN - 1]
                                    , DoComputeResolution=self.DoComputeResolution[iterN]
                                    , DoCtfCorrection=self.DoCtfCorrection
                                    , DoScale=self.DoScale
                                    , DoParallel=self.DoParallel
                                    , InnerRadius=self.InnerRadius[iterN]
                                    , MaxChangeOffset=self.MaxChangeOffset[iterN]
                                    , MpiJobSize=self.MpiJobSize
                                    , NumberOfMpi=self.NumberOfMpi
                                    , NumberOfThreads=self.NumberOfThreads
                                    , OuterRadius=self.OuterRadius[iterN]
                                    , PaddingFactor=self.PaddingFactor
                                    , ProjectLibraryRootName=projLibFn
                                    , ProjMatchRootName=ProjMatchRootName
                                    , ReferenceIsCtfCorrected=self.ReferenceIsCtfCorrected[iterN]
                                    , ScaleStep=self.ScaleStep[iterN]
                                    , ScaleNumberOfSteps=self.ScaleNumberOfSteps[iterN]
                                    , Search5DShift=self.Search5DShift[iterN]
                                    , Search5DStep=self.Search5DStep[iterN]
                                    )

            
            #assign the images to the different references based on the crosscorrelation coefficient
            #if only one reference it just copy the docfile generated in the previous step
            _dataBase.insertStep('assign_images_to_references', verifyfiles=[self.DocFileInputAngles[iterN]]
                                     , BlockWithAllExpImages = self.BlockWithAllExpImages
                                     , DocFileInputAngles=self.DocFileInputAngles[iterN]#Output file with angles
                                     , CtfGroupDirectory = self.CtfGroupDirectory
                                     , CtfGroupRootName = self.CtfGroupRootName                           
                                     , ProjMatchRootName=ProjMatchRootNameList#LIST
                                     , NumberOfReferences=self.numberOfReferences
                         )
    
            #align images, not possible for ctf groups
            _VerifyFiles = [self.getFilename('OutClassesDiscarded', iter=iterN)]
            _VerifyFiles = _VerifyFiles + [self.getFilename('OutClassesXmd', iter=iterN, ref=g) \
                                     for g in range (1, self.numberOfReferences + 1)]
            _VerifyFiles = _VerifyFiles + [self.getFilename('OutClassesStk', iter=iterN, ref=g) \
                                     for g in range (1, self.numberOfReferences + 1)]

            _dataBase.insertStep('angular_class_average', verifyfiles=_VerifyFiles
                             , Align2DIterNr=self.Align2DIterNr[iterN]#
                             , Align2dMaxChangeOffset=self.Align2dMaxChangeOffset[iterN]#
                             , Align2dMaxChangeRot=self.Align2dMaxChangeRot[iterN]#
                             , CtfGroupDirectory=self.CtfGroupDirectory#
                             , CtfGroupRootName=self.CtfGroupRootName#
                             , DiscardImages=self.DiscardImages#
                             , DiscardPercentage=self.DiscardPercentage[iterN]#
                             , DiscardPercentagePerClass=self.DiscardPercentagePerClass[iterN]#
                             , DoAlign2D=self.DoAlign2D[iterN]#
                             , DoComputeResolution=self.DoComputeResolution[iterN]
                             , DoCtfCorrection=self.DoCtfCorrection#
                             , DocFileInputAngles=self.DocFileInputAngles[iterN]#
                             , DoParallel=self.DoParallel
                             , DoSaveImagesAssignedToClasses=self.DoSaveImagesAssignedToClasses#
                             , DoSplitReferenceImages=self.DoSplitReferenceImages[iterN]#
                             , InnerRadius=self.InnerRadius[iterN]#
                             , MaxChangeOffset=self.MaxChangeOffset[iterN]#
                             , MinimumCrossCorrelation=self.MinimumCrossCorrelation[iterN]#
                             , MpiJobSize=self.MpiJobSize
                             , NumberOfMpi=self.NumberOfMpi
                             , NumberOfThreads=self.NumberOfThreads
                             , OutClasses=self.getFilename('OutClasses', iter=iterN)#
                             , PaddingFactor=self.PaddingFactor#
                             , ProjectLibraryRootName=self.getFilename('ProjectLibraryStk', iter=iterN, ref=refN)#
                             )
            

            for refN in range(1, self.numberOfReferences + 1):
                def insertReconstructStep(verifyFilesKey, inputMdKey, outputVolKey):
                    _VerifyFiles = [self.getFilename(verifyFilesKey, iter=iterN, ref=refN)]
                    self.insertStep('reconstruction', verifyfiles=_VerifyFiles
                                          , ARTReconstructionExtraCommand = self.ARTReconstructionExtraCommand
                                          , WBPReconstructionExtraCommand = self.WBPReconstructionExtraCommand
                                          , FourierReconstructionExtraCommand = self.FourierReconstructionExtraCommand
                                          , Iteration_number  = iterN
                                          , DoParallel=self.DoParallel#
                                          , maskedFileNamesIter=maskedFileName
                                          , MpiJobSize=self.MpiJobSize
                                          , NumberOfMpi=self.NumberOfMpi#
                                          , NumberOfThreads=self.NumberOfThreads#
                                          , ReconstructionMethod = self.ReconstructionMethod
                                          , FourierMaxFrequencyOfInterest = self.FourierMaxFrequencyOfInterest[iterN]
                                          , ARTLambda = self.ARTLambda
                                          , SymmetryGroup = self.SymmetryGroup[iterN]
                                          , ReconstructionXmd = self.getFilename(inputMdKey, iter=iterN, ref=refN)
                                          , ReconstructedVolume = self.getFilename(outputVolKey, iter=iterN, ref=refN)
                                          , PaddingFactor = self.PaddingFactor
                                          , ResolSam = self.ResolSam
                                          , ResolutionXmdPrevIterMax = self.getFilename('ResolutionXmdMax', iter=iterN-1, ref=refN)
                                          , ConstantToAddToFiltration = self.ConstantToAddToMaxReconstructionFrequency[iterN]
                                          )
    
                #self._ReconstructionMethod=arg.getComponentFromVector(_ReconstructionMethod, iterN-1)
                #self._ARTLambda=arg.getComponentFromVector(_ARTLambda, iterN-1)

                #if (DoReconstruction):
                insertReconstructStep('ReconstructedFileNamesIters', 'ReconstructionXmd', 'ReconstructedFileNamesIters')                
                    
                if(self.DoSplitReferenceImages[iterN]):
                    insertReconstructStep('ReconstructedFileNamesItersSplit1', 'ReconstructionXmdSplit1', 'ReconstructedFileNamesItersSplit1')      
                    insertReconstructStep('ReconstructedFileNamesItersSplit2', 'ReconstructionXmdSplit2', 'ReconstructedFileNamesItersSplit2')
                    
                    _VerifyFiles = [self.getFilename('ResolutionXmdFile', iter=iterN, ref=refN)]
                    id = _dataBase.insertStep('compute_resolution', verifyfiles=_VerifyFiles
                                                 , ConstantToAddToFiltration = self.ConstantToAddToMaxReconstructionFrequency[iterN]
                                                 , FourierMaxFrequencyOfInterest = self.FourierMaxFrequencyOfInterest[iterN]
                                                 , ReconstructionMethod = self.ReconstructionMethod
                                                 , ResolutionXmdCurrIter = self.getFilename('ResolutionXmd', iter=iterN, ref=refN)
                                                 , ResolutionXmdCurrIterMax = self.getFilename('ResolutionXmdMax', iter=iterN, ref=refN)
                                                 , ResolutionXmdPrevIterMax = self.getFilename('ResolutionXmdMax', iter=iterN-1, ref=refN)
                                                 , OuterRadius = self.OuterRadius[iterN]
                                                 , ReconstructedVolumeSplit1 = self.getFilename('ReconstructedFileNamesItersSplit1', iter=iterN, ref=refN)
                                                 , ReconstructedVolumeSplit2 = self.getFilename('ReconstructedFileNamesItersSplit2', iter=iterN, ref=refN)
                                                 , ResolSam = self.ResolSam
                                                  )

                    id = _dataBase.insertStep('filter_volume', verifyfiles=_VerifyFiles
                                              , FourierMaxFrequencyOfInterest = self.FourierMaxFrequencyOfInterest[iterN+1]
                                              , ReconstructedVolume = self.getFilename('ReconstructedFileNamesIters', iter=iterN, ref=refN)
                                              , ReconstructedFilteredVolume = self.reconstructedFilteredFileNamesIters[iterN][refN]
                                              , DoComputeResolution = self.DoComputeResolution
                                              , OuterRadius = self.OuterRadius
                                              , DoLowPassFilter = self.DoLowPassFilter
                                              , UseFscForFilter = self.UseFscForFilter
                                              , ConstantToAddToFiltration = self.ConstantToAddToMaxReconstructionFrequency[iterN]
                                              #, ConstantToAddToFiltration = 0.
                                              , ResolutionXmdPrevIterMax = self.getFilename('ResolutionXmdMax', iter=iterN, ref=refN)
                                              , ResolSam = self.ResolSam
                                              )
        _dataBase.connection.commit()

    def otherActionsToBePerformedAfterLoop(self):
        _log = self.Log
        _dataBase = self.Db
        #creating results files
        lastIteration   = self.NumberOfIterations
        inDocfile       = self.getFilename('DocfileInputAnglesIters', iter=lastIteration)
        resultsImages   = self.workingDirPath("results_images.xmd")
        resultsClasses  = self.workingDirPath("results_classes.xmd")

        _dataBase.insertStep('createResults'
                            , verifyfiles     = [resultsImages,resultsClasses]
                            , CTFDatName      = self.CTFDatName
                            , DoCtfCorrection = self.DoCtfCorrection
                            , inDocfile       = inDocfile
                            , resultsImages   = resultsImages
                            , resultsClasses  = resultsClasses
                            )
        _dataBase.connection.commit()
        
    def defineSteps(self):
        self.preRun()
        self.otherActionsToBePerformedBeforeLoop()
        self.actionsToBePerformedInsideLoop()
        self.otherActionsToBePerformedAfterLoop()

