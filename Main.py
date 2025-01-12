import os
import Reaction as rxn
import Trajectory
import inout as io
import MasterEq
import ConnectTools as CT
from shutil import copyfile
import multiprocessing
import numpy as np
from ase import Atoms

# Function to minimise the reactant geometry
def minReac(name):
    print('minimising', name)
    name.optReac()
    return name

# Function to run trajectories from current reactant and characterise the key paths
def runNormal(p):
    try:
        #If additional atoms have been added then update baseline dictionary
        #This only occurs when an extra bimolecular channel is added
        if len(p) > 6:
            print("correcting baseline for bi reaction")
            sym = "".join(p[6].get_chemical_symbols())
            TotSym = "".join(p[0].CombReac.get_chemical_symbols())
            print(str(sym) + " " + str(TotSym))
            base= p[0].energyDictionary[TotSym]
            p[0].energyDictionary[TotSym+sym] = p[0].TempBiEne(p[6])+base
            print(str(base))
        # Run Trajectory
        p[1].runTrajectory()
        print('trajectory done')
        print(p[1].productGeom)
        # Geom opt part
        # Optimise Product
        p[0].optProd(p[1].productGeom, False)

        #Get prod Name and create directory
        prodpath = p[2] + '/' + str(p[0].ProdName)

        #Get the indicies of the bonds which have either formed or broken over the course of the reaction
        changedBonds = CT.getChangedBonds(p[0].CombReac, p[0].CombProd)
        print('changesBonds ' + str(changedBonds))
        print(str(p[0].ProdName))
        # Check the reaction product is not the orriginal reactant
        if p[0].ProdName != p[0].ReacName:

            # Make Directory for product
            if not os.path.exists(prodpath):
                os.makedirs(prodpath)
                p[0].printProd(prodpath)


                # TS optimisation
                try:
                    p[0].optTSpoint(changedBonds, prodpath,p[1].MolList,p[1].TSpoint,0)
                except:
                    # If TS opt fails for some reason, assume barrierless
                    print('Couldnt opt TS at trans point')
                    p[0].barrierlessReaction = True

                printTS2 = False
                printXML = True


                if p[0].TScorrect != True:
                    # See whether a dynamical path calculation or an NEB calculation has been specified to refine TS
                    if p[5].printDynPath == True:
                        try:
                            p[0].optDynPath( changedBonds, prodpath,p[1].MolList, p[1].TSpoint)
                        except:
                            print("DynPath failed")
                    elif p[5].printNEB ==True:
                        try:
                            p[0].optNEB(changedBonds, prodpath, p[1].changePoints,p[1].MolList)
                        except:
                            print("NEB failed")
                    if p[0].TS2correct == True:
                        printTS2 = True

                # check whether there is an alternate product
                #if p[0].checkAltProd == True and p[0].is_IntermediateProd == True:
                #    p[0].optProd(p[1].productGeom, True)

                # Check some criteria before printing to xml
                # if Isomerisation check there is a TS
                if p[0].is_bimol_prod == False and p[0].is_bimol_reac == False and p[0].barrierlessReaction == True:
                    p[0].barrierlessReaction = False
                    printXML = True


                #Then check barrier isnt ridiculous
                if (((p[0].forwardBarrier - p[0].reactantEnergy) * 96.45) > 500):
                   printXML = False
                   print('channel barrier too large')

                # Finally check that the product isnt higher in energy than the reactant in case of ILT
                if p[0].is_bimol_reac == True and p[0].barrierlessReaction == True and p[0].reactantEnergy < p[0].productEnergy:
                    printXML = False


                if printXML == True:
                    try:
                        io.writeTSXML(p[0], p[3])
                        io.writeTSXML(p[0], p[3].replace('.xml','Full.xml'))
                    except:
                        print('Couldnt print TS1')

                    if printTS2 == True:
                        try:
                            io.writeTSXML2(p[0], p[3])
                            io.writeTSXML2(p[0], p[3].replace('.xml','Full.xml'))
                        except:
                            print('Couldnt print TS2')
                                    

                    tmppath = p[3].replace('/MESMER/mestemplate.xml','/')
                    tmppath = tmppath + p[0].ProdName

                    data = open(('MechanismData.txt'), "a")
                    data.write('Reactant = ' + str(p[0].ReacName) + ' Product = ' + str(p[0].ProdName) + ' BarrierHeight = ' +  str((p[0].forwardBarrier - p[0].reactantEnergy) * 96.45) + '\n' )

                    if not os.path.exists(tmppath):
                        io.writeMinXML(p[0], p[3], False, False)
                        if p[0].is_bimol_prod == True:
                            io.writeMinXML(p[0], p[3], False, True)
                    if not os.path.exists(tmppath + "/" + p[0].ReacName):
                        io.writeReactionXML(p[0], p[3], printTS2)
                        io.writeReactionXML(p[0], p[3].replace('.xml','Full.xml'), printTS2)

        if (p[5].InitialBi == True):
            p[0].re_init_bi(p[5].cartesians, p[5].species)
        else:
            p[0].re_init(p[2])
        return p[0],p[1]
    except:
        if (p[5].InitialBi == True):
            p[0].re_init_bi(p[5].cartesians, p[5].species)
        else:
            p[0].re_init(p[2])
        return p[0],p[1]

def run(glo):

    # Get path to current directory
    path = os.getcwd()

    #Check whether there is a directory for putting calcuation data in. If not create it
    if not os.path.exists(path + '/Raw'):
        os.mkdir(path + '/Raw')

    #Set restart bool for now
    glo.restart = True

    # Add system name to path
    syspath = path + '/' + glo.dirName


    #Make working directories for each core
    for i in range(0,glo.cores):
        if not os.path.exists(path + '/Raw/' + str(i)):
            os.mkdir(path + '/Raw/' + str(i))

    #Start counter which tracks the kinetic timescale
    mechanismRunTime = 0.0

    #Set reaction instance
    reacs = dict(("reac_" + str(i), rxn.Reaction(glo.cartesians, glo.species, i, glo)) for i in range(glo.cores))

    #Initialise Master Equation object
    me = MasterEq.MasterEq()

    # Open files for saving summary
    mainsumfile = open(( 'mainSummary.txt'), "a")

    while mechanismRunTime < glo.maxSimulationTime:

        # Minimise starting Geom and write summary xml for channel
        if reacs['reac_0'].have_reactant == False:
            outputs = []
            if __name__ == 'Main':
                arguments = []
                for i in range(0,glo.cores):
                    name = 'reac_' + str(i)
                    arguments.append(reacs[name])
                p = multiprocessing.Pool(glo.cores)
                results = p.map(minReac, arguments)
                outputs = [result for result in results]

            for i in range(0,glo.cores):
                name = 'reac_' + str(i)
                reacs[name] = outputs[i]

        else:
            for i in range(0,glo.cores):
                name = 'reac_' + str(i)
                reacs[name].have_reactant = False


        # Update path for new minima
        minpath  = syspath + '/' + reacs['reac_0'].ReacName

        # Get smiles name for initial geom and create directory for first minimum
        if not os.path.exists(minpath):
            os.makedirs(minpath)

        #Copy MESMER file from mes folder
        MESpath = syspath +  '/MESMER/'
        symb = "".join(reacs[name].CombReac.get_chemical_symbols())
        if reacs['reac_0'].energyDictionary[symb] == 0.0:
                for i in range(0,glo.cores):
                    name = 'reac_' + str(i)
                    d = {symb:reacs[name].reactantEnergy}
                    reacs[name].energyDictionary.update(d)



        # If a MESMER file has not been created for the current minima then create one
        if not os.path.exists(MESpath):
            os.makedirs(MESpath)
            copyfile('mestemplate.xml', MESpath + 'mestemplate.xml' )
            copyfile('mestemplate.xml', MESpath + 'mestemplateFull.xml' )
            MESFullPath = MESpath  + 'mestemplateFull.xml'
            MESpath = MESpath + 'mestemplate.xml'
            io.writeMinXML(reacs['reac_0'], MESpath, True, False)
            io.writeMinXML(reacs['reac_0'], MESFullPath, True, False)
            if reacs['reac_0'].is_bimol_reac == True:
                io.writeMinXML(reacs['reac_0'], MESpath, True, True)
                io.writeMinXML(reacs['reac_0'], MESFullPath, True, True)
            glo.restart = False
        else:
            MESFullPath = MESpath + 'mestemplateFull.xml'
            MESpath = MESpath + 'mestemplate.xml'

        # If this is a restart then need to find the next new product from the ME, otherwise start trajectories
        if glo.restart == False:
            # Open files for saving summary
            sumfile = open((minpath + '/summary.txt'), "w")

            reacs['reac_0'].printReac(minpath)
            for r in range(0,glo.ReactIters):
                tempPaths = dict(("tempPath_" + str(i),minpath +'/temp' + str(i) + '_' + str(r)) for i in range(glo.cores))
                # Now set up tmp directory for each thread
                for i in range(0,glo.cores):
                    if not os.path.exists(tempPaths[('tempPath_' + str(i))]):
                        os.makedirs(tempPaths[('tempPath_' + str(i))])
        
                if r % 2 == 0:
                    glo.trajMethod = glo.trajMethod1
                    glo.trajLevel = glo.trajLevel1
                else:
                    glo.trajMethod = glo.trajMethod2
                    glo.trajLevel = glo.trajLevel2

                # If this is the first species and it is a bimolecular channel, then initialise a bimolecular trajectory
                # Otherwise initialise unimolecular trajectory at minima
                if glo.InitialBi ==True:
                    trajs = dict(("traj_" + str(i), Trajectory.Trajectory(reacs[('reac_' + str(i))].CombReac, glo, tempPaths[('tempPath_' + str(i))], str(i),True)) for i in range(glo.cores))
                else:
                    trajs = dict(("traj_" + str(i), Trajectory.Trajectory(reacs[('reac_' + str(i))].CombReac, glo, tempPaths[('tempPath_' + str(i))], str(i),False)) for i in range(glo.cores))

                results2=[]
                outputs2=[]
                if __name__ == "Main":
                    arguments1 = []
                    arguments2 = []
                    for i in range(0,glo.cores):
                        name = 'reac_' + str(i)
                        name2 = 'traj_' + str(i)
                        arguments1.append(reacs[name])
                        arguments2.append(trajs[name2])
                    arguments = list(zip(arguments1, arguments2, [minpath] * glo.cores, [MESpath] * glo.cores, range(glo.cores), [glo] * glo.cores))
                    p = multiprocessing.Pool(glo.cores)
                    results2 = p.map(runNormal, arguments)
                    outputs2 = [result for result in results2]

                for i in range(0,glo.cores):
                    name = 'reac_' + str(i)
                    reacs[name] = outputs2[i][0]
                    sumfile.write(str(reacs[name].ProdName) + '_' + str(reacs[name].biProdName) + '\t' + str(reacs[name].forwardBarrier) + '\t' + str(outputs2[i][1].numberOfSteps))
                    sumfile.flush()

            # run a master eqution to estimate the lifetime of the current species
            me.runTillReac(MESpath)
            me.newSpeciesFound = False


            # check whether there is a possible bimolecular rection for current intermediate
            if len(glo.BiList) > 0 and glo.InitialBi == False:
                for i in range(0,len(glo.BiList)):
                    baseXYZ = reacs['reac_0'].CombReac.get_chemical_symbols()
                    if me.time > (1 / float(glo.BiRates[i])):
                        print("assessing whether or not to look for bimolecular channel. Rate = " + str(float(glo.BiRates[i])) + "Mesmer reaction time = " + str(me.time))
                        glo.InitialBi = True
                        xyz = CT.get_bi_xyz(reacs['reac_0'].ReacName, glo.BiList[i])
                        spec = np.append(baseXYZ,np.array(glo.BiList[i].get_chemical_symbols()))
                        combinedMol = Atoms(symbols=spec, positions = xyz)
                        #Set reaction instance
                        for j in range(0,glo.cores):
                            name = 'reac_' + str(j)
                            d = {symb:reacs[name].reactantEnergy}
                            reacs[name].re_init_bi(xyz, spec)
                            biTrajs = dict(("traj_" + str(k), Trajectory.Trajectory(combinedMol, glo, tempPaths[('tempPath_' + str(k))], str(k), True)) for k in range(glo.cores))
                            biTempPaths = dict(("tempPath_" + str(k),minpath +'/temp' + str(j)) for k in range(glo.cores))
                        if __name__ == "Main":
                            arguments1 = []
                            arguments2 = []
                            for j in range(0,glo.cores):
                                name = 'reac_' + str(j)
                                name2 = 'traj_' + str(j)
                                biTrajs[name2].fragIdx = (len(baseXYZ),len(xyz))
                                arguments1.append(reacs[name])
                                arguments2.append(biTrajs[name2])
                            arguments = list(zip(arguments1, arguments2, [minpath] * glo.cores, [MESpath] * glo.cores, range(glo.cores), [glo] * glo.cores, [glo.BiList[i]] * glo.cores ))
                            p = multiprocessing.Pool(glo.cores)
                            p.map(runNormal, arguments)
                            glo.InitialBi = False

            # Run ME from the given minimum. While loop until species formed is new
            sumfile.close()
            glo.restart = False
        glo.InitialBi = False
        while me.newSpeciesFound == False:
            me.runTillReac(MESpath)
            mechanismRunTime += me.time
            out = me.prodName + '     ' + str(mechanismRunTime) + '\n'
            me.visitedList.append(me.prodName)
            mainsumfile.write(out)
            mainsumfile.flush()
            if not os.path.exists(syspath + '/' + me.prodName):
                os.makedirs(syspath+ '/' + me.prodName)
                for i in range(0,glo.cores):
                    if os.path.exists(syspath + '/' + reacs[('reac_' + str(i))].ReacName + '/' + me.prodName):
                        reacs[('reac_' + str(i))].newReac(syspath + '/' + reacs[('reac_' + str(i))].ReacName + '/' + me.prodName,  me.prodName, False)
                    else:
                        print ("cant find path " + str(syspath + '/' + reacs[('reac_' + str(i))].ReacName + '/' + me.prodName))
                        try:
                            reacs[('reac_' + str(i))].newReac(syspath + '/' + me.prodName,  me.prodName, True)
                        except:
                            reacs[('reac_' + str(i))].newReacFromSMILE(me.prodName)
                io.update_me_start(me.prodName, me.ene, MESpath)
                me.newSpeciesFound = True
            else:
                if me.repeated() == True:
                    me.equilCount += 1
                    if me.equilCount >= 20:
                        mainsumfile.write('lumping'+ ' ' + str(reacs['reac_0'].ReacName) + ' ' + str(me.prodName) + '\n')
                        me.prodName = io.lumpSpecies( reacs['reac_0'].ReacName, me.prodName, MESpath, MESpath)
                        mainsumfile.flush()
                        me.equilCount = 1
                minpath = syspath + '/' + me.prodName
                for i in range(0,glo.cores):
                    if os.path.exists(syspath + '/' + reacs[('reac_' + str(i))].ReacName + '/' + me.prodName):
                        reacs[('reac_' + str(i))].newReac(syspath + '/' + reacs[('reac_' + str(i))].ReacName + '/' + me.prodName,  me.prodName, False)
                    else:
                        try:
                            reacs[('reac_' + str(i))].newReac(syspath + '/' + me.prodName,  me.prodName, True)
                        except:
                            reacs[('reac_' + str(i))].newReacFromSMILE(me.prodName)
                io.update_me_start(me.prodName, me.ene, MESpath)

        me.newspeciesFound = False
        glo.restart = False


    mainsumfile.close()











