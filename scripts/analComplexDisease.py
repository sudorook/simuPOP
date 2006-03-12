#!/usr/bin/env python
#
# Purpose:  generate dataset for common complex disease 
#           with certain number of disease susceptibility
#           loci.
#
# Bo Peng (bpeng@rice.edu)
#
# $LastChangedDate: 2005-10-31 17:29:34 -0600 (Mon, 31 Oct 2005) $
# $Rev: 78 $
#
# Known bugs:
#   None
# 

"""

Introduction
=============

This program analyze the dataset generated by simuComplexDisease.py, it will

  1. Apply single or multi-locus penetrance functions to determine 
     affectedness of each individual. Note that the penetrance model would
     better be compatible to the fitness model. You would not want to assign
     affectedness to individuals according to disease susceptibility locus 
     (DSL) one while selection was working on DSL two.
  2. Draw population and/or pedigree based samples are drawn and saved in popular
     formats.
  3. If geneHunter is available, it will be used to analyze affected sibpair 
     samples using TDT method.

Please refer to simuComplexDisease.py and see how the dataset is generated.

The program is written in Python using simuPOP modules. For more information,
please visit simuPOP website http://simupop.sourceforge.net .


Penetrance
==========

Since we assume that fitness only depends on genotype, not affectedness status,
we do not care who are affected during evolution. This has to change at the 
last generation where different sampling schemes will be applied to the 
population. Several customizable penetrance schemes will be used. As a matter
of fact, if there is no selection against any DS allele, we can use any
of the penetrance functions:

  1. recessive single-locus and heterogeneity multi-locus model: 
    At DSL i , penetrance will be computed as
      0, 0, p_i
    for genotype
      AA, Aa, aa  (A is wild type)
    where pi are penetrance factors (that can vary between DSL).

    The overall penetrance is 
      1 - Prod(1-P_i)
    where Pi is the penetrance at locus i.
  
  2. additive single-locus and heterogeneity multi-locus model: 
    For each DSL, the penetrance is
      0, p/2, p
    for genotype
      AA, Aa, aa
    where the overall penetrance takes the form of
      1 - Prod( 1- P_i)
    This is the heterogeneity model proposed by Neil Risch (1990).
     
  3. Customized, you can write your own penetrance function here.
  
Samples and Output
==================

Different kinds of samples will be draw from the final large population.

  1. population based case control sample: 
     Regardless of family structure, N cases and N controls will
     be drawn randomly.
  
  2. affected and unaffected sibpairs:
     N/4 affected and N/4 unaffected (sibling) families (two siblings and
     two parents) will be drawn. (Sample size is N cases and N controls
     when counting individuals.)

The datasets will be saved in native simuPOP format and in Linkage format.
DSL markers will be removed so there will be no marker that is directly 
linked to the disease.

All files are put under a specified folder. They are organized by
penetrance methods. A html file summary.htm will be automatically 
generated with links to all statistics, datasets etc.


Gene mapping
============

If the location of genehunter is specified. It will be applied to all affected
sibpair samples. This is the raw one-locus TDT method with no correction on things
like multiple testing.

"""

import simuOpt, simuUtil
import os, sys, types, exceptions, os.path, re, math, time, copy, operator

#
# declare all options. getParam will use these information to get parameters
# from a tk/wxPython-based dialog, command line, config file or user input
#
# detailed information about these fields is given in the simuPOP reference
# manual.
options = [
  {'arg': 'h',
   'longarg': 'help',
   'default': False, 
   'description': 'Print this usage message.',
   'allowedTypes': [types.NoneType, type(True)],
   'jump': -1          # if -h is specified, ignore any other parameters.
  },
  {'longarg': 'markerType=',
   'default': 'microsatellite',
   'allowedTypes': [types.StringType],
   'configName': 'Marker type used',
   'prompt': 'Marker type used (microsatellite)',
   'description': '''Marker type used to generated the sample. This is important
         since the file formats are not compatible between binary and standard
         simuPOP modules''',
   'validate':  simuOpt.valueOneOf([ 'microsatellite', 'SNP']),
   'chooseOneOf': ['microsatellite', 'SNP']
  }, 
  {'longarg': 'wildtype=',
   'default': 0,
   'allowedTypes': [types.IntType],
   'configName': 'Wildtype allele',
   'prompt': 'Wildtype allele',
   'description': '''Wildtype should be 0 but microsatellite datasets generated 
         before rev 225 uses 1 as wildtype. Set this variable to avoid trouble.''',
   'validate':  simuOpt.valueOneOf([ 0, 1]),
   'chooseOneOf': [0, 1]
  },
  {'longarg': 'dataset=',
   'default': 'simu.bin',
   'allowedTypes': [types.StringType],
   'configName': 'Dataset to analyze',
   'prompt': 'Dataset to analyze (simu.bin):  ',
   'description': 'Dataset generated by simuComplexDisease.py. ',
   'validate':  simuOpt.valueValidFile()
  },
  {'longarg': 'saveFormat=',
   'default': ['simuPOP','Linkage'],
   'configName': 'Save in formats',
   'allowedTypes': [types.ListType, types.TupleType],
   'prompt': "Save datasets in format (['simuPOP','Linkage','randTent']):  ",
   'description': '''Save generated datasets in specified formats.
        Choosen from simuPOP, Linkage, randTent. ''',
   'validate':  simuOpt.valueListOf( simuOpt.valueOneOf([ 'simuPOP', 'Linkage'])),
   'chooseFrom': [ 'simuPOP', 'Linkage']
  },
  {'longarg': 'peneFunc=',
   'default': ['recessive','additive'],
   'configName': 'Penetrance functions',
   'allowedTypes': [types.ListType, types.TupleType],
   'prompt': 'Penetrance to be used: (recessive, additive):  ',
   'description': ''' Penetrance functions to be applied to the final
        population. Two penetrance fucntions are provided, namely recessive or additive
	single-locus model with heterogeneity multi-locus model. You can define another
	customized penetrance functions by modifying this script. ''',
   'allowedTypes': [types.ListType, types.TupleType],
   'validate':  simuOpt.valueListOf( simuOpt.valueOneOf(['recessive', 'additive', 'custom'])),
   'chooseFrom': [ 'recessive', 'additive', 'custom']
  },
  {'longarg': 'penePara=',
   'default': [0.5],
   'configName': 'Penetrance parameters',
   'prompt': 'Penetrance parameter used by penetrance functions. \n' + 
      "Can be an array (for each DSL). (0.5) ",
   'description': '''Penetrance parameter for all DSL. An array of parameter 
        can be given to each DSL. The meaning of this parameter differ by penetrance model.
        For a recessive model, the penetrance is 0,0,p for genotype AA,Aa,aa (a is disease
        allele) respectively. For an additive model, the penetrance is 0,p/2,p respectively.
        A list of parameter can be given for each penetrance model in the form of 
        [[.1,.2],[.1],[.2]] ''',
   'allowedTypes': [types.ListType, types.TupleType],
   'validate':  simuOpt.valueListOf( simuOpt.valueOneOf([ 
       simuOpt.valueBetween(0,1), simuOpt.valueListOf(simuOpt.valueBetween(0,1))] ) )
  },
  {'longarg': 'sampleSize=',
   'default': 800,
   'configName':  'Sample size',
   'allowedTypes':  [types.IntType, types.LongType],
   'prompt':  'Size of the samples (800):  ',
   'description':  '''Size of the samples, that will mean N/4 affected sibpair families (of size 4),
        N/2 cases and controls etc. ''',
   'validate':  simuOpt.valueGT(1)
  },
  {'longarg': 'numSample=',
   'default': 2,
   'configName':  'Sample number',
   'allowedTypes':  [types.IntType, types.LongType],
   'prompt':  'Number of samples for each penetrance function (2):  ',
   'description':  '''Number of samples to draw for each penetrance function. ''',
   'validate':  simuOpt.valueGT(0)
  },
  {'longarg': 'outputDir=',
   'default': '.',
   'allowedTypes': [types.StringType],
   'configName': 'Output directory',
   'prompt': 'Save datasets into directory (.):  ',
   'description': 'Directory into which the datasets will be saved. ',
   'validate':  simuOpt.valueValidDir()
  },
  {'longarg': 'geneHunter=',
   'default': 'gh',
   'allowedTypes': [types.StringType],
   'configName': 'Location of gene hunter',
   'prompt': 'Provide location of gene hunter ():  ',
   'description': '''Location of gene hunter executable. If provided,
        the TDT and Linkage method of genehunter will be applied to affected sibpair 
        samples.'''
  },
  # another two hidden parameter
  {'longarg': 'reAnalyzeOnly=',
   'default': False,
   'allowedTypes': [type(True)],
   'description': '''If given in command line, redo the analysis.'''
  },
  {'longarg': 'saveConfig=',
   'default': 'anal.cfg',
   'allowedTypes': [types.StringType, types.NoneType],
   'configName': 'Save configuration',
   'prompt': 'Save current configuration to file (anal.cfg):  ',
   'description': 'Save current paremeter set to specified file.'
  },
  {'arg': 'v',
   'longarg': 'verbose',
   'default': False,
   'allowedTypes': [types.NoneType, types.IntType],
   'description': 'Verbose mode.'
  },
]

# __doc__ + parameter definitions use >500 lines, 
# more than one third of the total length of the script.

def getOptions(details=__doc__):
  ''' get options from options structure,
    if this module is imported, instead of ran directly,
    user can specify parameter in some other way.
  '''
  # get all parameters, __doc__ is used for help info
  allParam = simuOpt.getParam(options, 
    '''  This program simulates the evolution of a complex common disease, subject 
   to the impact of mutation, migration, recombination and population size change. 
   Click 'help' for more information about the evolutionary scenario.''', details, nCol=2)
  # when user click cancel ...
  if len(allParam) == 0:
    sys.exit(1)
  # -h or --help
  if allParam[0]:  
    print simuOpt.usage(options, __doc__)
    sys.exit(0)
  # --saveConfig
  simuOpt.saveConfig(options, allParam[-2], allParam)
  # --verbose or -v (these is no beautifying of [floats]
  if allParam[-1]:         # verbose
    simuOpt.printConfig(options, allParam)
  # return the rest of the parameters
  return allParam[1:-2]

# plot the LD values for the sample.
def plotLD(pop, epsFile, jpgFile):
  ''' plot D' values in R and convert to jpg if possible,
    all the values are stored in pop.dvars() '''
  vars = pop.dvars()
  # return max LD
  res = {}
  # dist: distance (location) of marker
  # ldprime: D' value
  dist = []
  ldprime = [] # D'
  ldvalue = [] # D
  for ld in vars.ctrDSLLD:
    if ld[1] == vars.ctrChromDSL:
      dist.append(pop.locusPos(ld[0]))
    else:
      dist.append(pop.locusPos(ld[1]))
    ldprime.append(vars.LD_prime[ld[0]][ld[1]])
    ldvalue.append(vars.LD[ld[0]][ld[1]])
  res['DpDSL'] = max(ldprime)
  res['DDSL'] = max(ldvalue)
  if hasRPy:
    r.postscript(file=epsFile, width=8, height=8)
    r.par(mfrow=[2,1])
    r.plot( dist, ldprime, main="D' between DSL and other markers on chrom %d" % (vars.ctrChrom+1),
      xlab="marker location", ylab="D'", type='b', ylim=[0,1])
    r.abline( v = pop.locusPos(vars.ctrChromDSL), lty=3 )
    r.axis( 1, [pop.locusPos(vars.ctrChromDSL)], ['DSL'])
  dist = [] 
  ldprime = []  # D'
  ldvalue = []  # D
  if vars.noDSLChrom > -1:
    for ld in vars.noDSLLD:
      if ld[1] == pop.chromBegin(vars.noDSLChrom) + vars.numLoci/2:
        dist.append(pop.locusPos(ld[0]))
      else:
        dist.append(pop.locusPos(ld[1]))
      ldprime.append(vars.LD_prime[ld[0]][ld[1]])    
      ldvalue.append(vars.LD[ld[0]][ld[1]])    
    res['DpNon'] = max(ldprime)
    res['DNon'] = max(ldvalue)
    if hasRPy:
      r.plot( dist, ldprime, main="D' between marker %d and other markers on chrom %d" \
        % (vars.numLoci/2+1, vars.noDSLChrom+1),
        xlab="marker location", ylab="D'", type='b', ylim=[0,1])    
      r.abline( v = pop.locusPos(pop.chromBegin(vars.noDSLChrom)+vars.numLoci/2), lty=3 )
      r.dev_off()
  else:
    res['DpNon'] = 0
    res['DNon'] = 0
    if hasRPy:
      r.plot( 0, 0, main="There is no chromosome without DSL",
        xlab="marker location", ylab="D'", type='b', ylim=[0,1])    
      r.dev_off()
  # try to get a jpg file
  try:
    if os.system("convert -rotate 90 %s %s " % (epsFile, jpgFile) ) == 0:
      return (2,res)  # success
    else:
      return (1,res) # fail
  except:
    return (1,res)  # fail

# penetrance generator functions. They will return a penetrance function
# with given penetrance parameter
def recessive(pen, wt):
  ''' recessive single-locus, heterogeneity multi-locus '''
  def func(geno):
    val = 1
    for i in range(len(geno)/2):
      if geno[i*2]+geno[i*2+1] - 2*wt == 2:
        val *= 1 - pen
    return 1-val
  return func
  
def additive(pen, wt):
  ''' additive single-locus, heterogeneity multi-locus '''
  def func(geno):
    val = 1
    for i in range(len(geno)/2):
      val *= 1 - (geno[i*2]+geno[i*2+1]-2*wt)*pen/2.
    return 1-val
  return func

# if you need some specialized penetrance function, modify this
# function here.
# NOTE:
# 
# 1. geno is the genptype at DSL. For example, if your DSL is [5,10]
#   geno will be something like [0,1,1,1] where 0,1 is the genotype at 
#   locus 5.
# 2. in simuComplexDisease.py, 0 is wild type, 1 is disease allele.
def custom(pen, wt):
  ''' a penetrance function that focus on the first DSL '''
  def func(geno):
    return 1
  return func

def drawSamples(pop, peneFunc, penePara, wildtype, numSample, saveFormat, dataDir, reAnalyzeOnly ):
  ''' get samples of different type using a penetrance function,
    and save samples in dataDir in saveFormat
    
    pop: population
    peneFunc: penetrance function name, can be recessive1 etc
    penePara: parameter of the penetrance function
    numSample: number of samples for each penetrance settings
    saveFormat: a list of format to save
    dataDir: where to save samples    
    reAnalyzeOnly: load populations only

    return a report
  '''
  # first, apply peneFunction
  #
  report = ''
  if peneFunc.find('recessive') == 0:  # start with recessive
    print "Using recessive penetrance function"
    report += "<h4>Recessive single-locus, heterogeneity multi-locus</h4>\n"
    penFun = recessive(penePara, wildtype)
  elif peneFunc.find('additive') == 0: # start with additive
    print "Using additive penetrance function"
    report += "<h4>Additive single-locus, heterogeneity multi-locus</h4>\n"
    penFun = additive(penePara, wildtype)
  elif peneFunc.find('custom') == 0: # start with custom
    print "Using customized penetrance function"
    report += "<h4>Customized penetrance function</h4>\n"
    penFun = custom(penePara, wildtype)  
  # this may or may not be important. Previously, we only
  # set penetrance for the final genetion but linkage methods
  # may need penetrance info for parents as well.
  for i in range(0, pop.ancestralDepth()+1):
    # apply penetrance function to all current and ancestral generations
    pop.useAncestralPop(i)
    PyPenetrance(pop, loci=pop.dvars().DSL, func=penFun)
  # reset population to current generation.
  pop.useAncestralPop(0)
  #
  if saveFormat == []:
    return report
  # 
  report += "<ul>"
  # here we are facing a problem of using which allele frequency for the sample
  # In reality, if it is difficult to estimate population allele frequency,
  # sample frequency has to be used. Otherwise, population frequency should 
  # be used whenever possible. Here, we use population allele frequency, with only
  # one problem in that we need to remove frequencies at DSL (since samples do not
  # have DSL).
  af = []
  Stat(pop, alleleFreq=range(pop.totNumLoci()))
  for x in range( pop.totNumLoci() ):
    if x not in pop.dvars().DSL:
      af.append( pop.dvars().alleleFreq[x] )
  # start sampling
  for ns in range(numSample):
    report += "<li> sample %d <ul>" % (ns+1)
    penDir = "%s%s%s%d%s" % (dataDir, os.sep, peneFunc, ns, os.sep)
    # relative path used in report
    relDir = '%s%s%s%d%s' % (dataDir.split(os.sep)[-1], os.sep, peneFunc, ns, os.sep)
    # 
    _mkdir(penDir)
    if reAnalyzeOnly:
      print "Loading sample ", ns+1, ' of ', numSample
    else:
      print "Generating sample ", ns+1, ' of ', numSample
    # 1. population based case control
    # get number of affected
    Stat(pop, numOfAffected=True)
    print "Number of affected individuals: ", pop.dvars().numOfAffected
    print "Number of unaffected individuals: ", pop.dvars().numOfUnaffected
    nCase = min(pop.dvars().numOfAffected , N/2)
    nControl = min(pop.dvars().numOfUnaffected, N/2)
      
    try:
      # if N=800, 400 case and 400 controls
      binFile =  penDir + "caseControl.bin"
      if reAnalyzeOnly:
        try:
          # try to load previous sample
          s = [LoadPopulation(binFile)]
        except Exception, err:
          print "Can not load exisiting sample. Can not use --reAnalyzeOnly option"
          raise err
      else:
        s = CaseControlSample(pop, nCase, nControl)
        # remove DSL
        s[0].removeLoci(remove=pop.dvars().DSL)
      report += "<li> Case control sample of size %d, " % s[0].popSize()
      # process sample
      if 'simuPOP' in saveFormat:
        report += 'saved in simuPOP binary format:'
        if not reAnalyzeOnly:
          print "Write to simuPOP binary format"
          s[0].savePopulation(binFile)
        report += '<a href="%scaseControl.bin"> caseControl.bin</a> ' % relDir
      report += '</li>'
    except Exception, err:
      print "Can not draw case control sample. "
      print type(err), err
    #
    # 2. affected and unaffected sibpairs
    # this is difficult since simuPOP only has
    # methods to draw one kind of sibpairs and 
    try:
      # get number of affected/unaffected sibpairs
      # There may not be enough to be sampled
      AffectedSibpairSample(pop, countOnly=True)
      nAff = min(pop.dvars().numAffectedSibpairs, N/4)
      print "Number of (both) affected sibpairs: ", pop.dvars().numAffectedSibpairs
      AffectedSibpairSample(pop, chooseUnaffected=True, countOnly=True)
      print "Number of unaffected sibpairs: ", pop.dvars().numAffectedSibpairs
      nUnaff = min(pop.dvars().numAffectedSibpairs, N/4)
      # generate or load sample
      binFile1 = penDir + "affectedSibpairs.bin"
      binFile2 = penDir + "unaffectedSibpairs.bin"
      if reAnalyzeOnly:
        try:
          affected = [LoadPopulation(binFile1) ]
          unaffected = [LoadPopulation(binFile2) ]
        except Exception, err:
          print "can not load sample, please do not use --reAnalyzeOnly option"
          raise err
      else:
        #
        affected = AffectedSibpairSample(pop, name='sample1',
          size=nAff)
        # now chose unaffected. These samples will not overlap
        # 
        # NOTE: however, you may not be able to easily merge these two 
        # samples since they may shared parents.
        #
        # Use another name to avoid conflict since these sampled are stored
        # in local namespace
        unaffected = AffectedSibpairSample(pop, chooseUnaffected=True,
          name='sample2', size=nUnaff)
        # remove DSL
        affected[0].removeLoci(remove=pop.dvars().DSL)
        unaffected[0].removeLoci(remove=pop.dvars().DSL)
      # return sample
      #
      report += "<li> Affected sibpair sample of size %d (affected) %d (unaffected)" % \
        ( affected[0].popSize(), unaffected[0].popSize() ) 
      if 'simuPOP' in saveFormat:
        report += ' saved in simuPOP binary format:'
        report += '<a href="%saffectedSibpairs.bin"> affectedSibpairs.bin</a>, ' % relDir
        if not reAnalyzeOnly:
          print "Write to simuPOP binary format"
          affected[0].savePopulation(binFile1)
          unaffected[0].savePopulation(binFile2)
        report += '<a href="%sunaffectedSibpairs.bin"> unaffectedSibpirs.bin</a>, ' % relDir
      if 'Linkage' in saveFormat:
        report += ' saved in linkage format by chromosome:'
        linDir = penDir + "Linkage" + os.sep
        _mkdir(linDir)
        report +=  '<a href="%sLinkage">affected</a>, ' % relDir
        if not reAnalyzeOnly:
          print "Write to linkage format"
          for ch in range(0, pop.numChrom() ):
            SaveLinkage(pop=affected[0], popType='sibpair', output = linDir+"/Aff_%d" % ch,
              chrom=ch, recombination=pop.dvars().recRate[0],
              alleleFreq=af, daf=0.1)        
          for ch in range(0,pop.numChrom() ):
            SaveLinkage(pop=unaffected[0], popType='sibpair', output = linDir+"/Unaff_%d" % ch,
              chrom=ch, recombination=pop.dvars().recRate[0],                            
              alleleFreq=af, daf=0.1)        
        report += '<a href="%sLinkage">unaffected</a>' % relDir
      report += '</li>'
    except Exception, err:
      print type(err)
      print err
      print "Can not draw affected sibpars."
    report += "</ul></li>"
    # save these samples
  report += "</ul>"
  return report

# apply the TDT method of GeneHunter
def TDT(pop, geneHunter, cutoff, dataDir, data, epsFile, jpgFile):
  ''' use TDT method to analyze the results. Has to have rpy installed '''
  if not hasRPy or geneHunter in ['', 'none']:
    return (0,[])
  # write a batch file and call gh
  allPvalue = []
  print "Applying TDT method to affected sibpairs "
  for ch in range(pop.numChrom()):
    inputfile = dataDir+data+ "_%d" % ch
    if not os.path.isfile(inputfile + ".pre"):
      print "Ped file ", inputfile+".pre does not exist. Can not apply TDT method."
      return (0,[])
    # batch file
    f=open("ghTDT.cmd","w")
    f.write("load markers " + inputfile + ".dat\n")
    f.write("tdt " + inputfile + ".pre\n")
    f.close()
    # run gene hunter
    os.system(geneHunter + " < ghTDT.cmd > res.txt ")
    # get the result
    # ( I was using              
    # | grep '^loc' | tr -d 'a-zA-Z+-' > " + outputfile)
    # but this is not portable
    #
    # use re package
    # get only loc number and p-value
    scan = re.compile('loc(\d+)\s+- Allele \d+\s+\d+\s+\d+\s+[\d.]+\s+([\d.]+)\s*.*')
    minPvalue = [1]*(pop.dvars().numLoci-1)
    try:
      res = open("res.txt")  # read result
      for l in res.readlines():
        try:
          # get minimal p-value for all alleles at each locus
          (loc,pvalue) = scan.match(l).groups()
          if minPvalue[int(loc)-1] > float(pvalue):
            minPvalue[int(loc)-1] = float(pvalue)
        except:
          # does not match
          continue
      res.close()
    except:
      print "Can not open result file. TDT failed"
      return (0,[])
    # collect -log10 pvalue
    allPvalue.extend([-math.log10(max(x,1e-6)) for x in minPvalue])
    # There will be numLoci-1 numbers, pad to the correct length
    allPvalue.append(0)
  try:
    os.unlink('res.txt')
    os.unlink('ghTDT.cmd')
  except:
    pass
  # now, we need to see how TDT works with a set of p-values around pop.dvars().DSL
  # pop.dvars().DSL is global
  res = []
  for d in pop.dvars().DSL: 
    res.append( max(allPvalue[(d-2):(d+2)]))
  # use R to draw a picture
  r.postscript(file=epsFile, width=6, height=4)
  r.plot(allPvalue, main="-log10(P-value) at each marker (TDT method)",
    xlab="chromosome/markers", ylab="-log10 p-value", type='l', axes=False, ylim=[0.01, 5])
  r.box()
  r.abline( v = [pop.dvars().DSLafter[g]+pop.dvars().DSLdist[g] for g in range(len(pop.dvars().DSL))], lty=3)
  r.abline( h = cutoff )                       
  r.axis(1, [pop.dvars().numLoci*x for x in range(pop.numChrom())], [str(x+1) for x in range(pop.numChrom())])
  r.axis(2)
  r.dev_off()
  # try to get a jpg file
  try:
    if os.system("convert -rotate 90 %s %s " % (epsFile, jpgFile) ) == 0:
      return (2,res)  # success
    else:
      return (1,res) # fail
  except:
    return (1,res)  # fail

# apply the Linkage method of GeneHunter
def Linkage(pop, geneHunter, cutoff, dataDir, data, epsFile, jpgFile):
  ''' use Linkage method to analyze the results. Has to have rpy installed '''
  if not hasRPy or geneHunter in ['', 'none']: 
    return (0,[])
  # write a batch file and call gh
  allPvalue = []
  print "Applying Linkage (LOD) method to affected sibpairs "
  for ch in range(pop.numChrom()):
    inputfile = dataDir+data+ "_%d" % ch
    if not os.path.isfile(inputfile + ".pre"):
      print "Ped file ", inputfile+".pre does not exist. Can not apply TDT method."
      return (0,[])
    # batch file
    f=open("ghLOD.cmd","w")
    f.write("load markers " + inputfile + ".dat\n")
    f.write("single point on\n")
    f.write("scan pedigrees " + inputfile + ".pre\n")
    f.write("photo tmp.txt\n")
    f.write("total stat\n")
    f.write("q\n")
    f.close()
    # run gene hunter
    os.system(geneHunter + " < ghLOD.cmd > res.txt ")
    # get the result
    # ( I was using              
    # | grep '^loc' | tr -d 'a-zA-Z+-' > " + outputfile)
    # but this is not portable
    #
    # use re package
    # get only loc number and p-value
    # position (locxx) -- Lodscore -- NPL score -- p-value -- information
    scan = re.compile('loc(\d+)\s+[^\s]+\s+[^\s]+\s+([^\s]+)\s*.*')
    minPvalue = [1]*(pop.dvars().numLoci-1)
    try:
      res = open("tmp.txt")  # read result
      for l in res.readlines():
        try:
          # get minimal p-value for all alleles at each locus
          (loc,pvalue) = scan.match(l).groups()
          if minPvalue[int(loc)-1] > float(pvalue):
            minPvalue[int(loc)-1] = float(pvalue)
        except:
          # does not match
          #print l
          #print err
          continue
      res.close()
    except Exception, err:
      print type(err), err
      print "Can not open result file tmp.txt. LOD failed"
      return (0,[])
    # did not get anything
    if minPvalue == [1]*(pop.dvars().numLoci-1):
      print "Do not get any p-value, something is wrong"
    # collect -log10 pvalue
    allPvalue.extend([-math.log10(max(x,1e-6)) for x in minPvalue])
    # There will be numLoci-1 numbers, pad to the correct length
    allPvalue.append(0)
    try:
      os.unlink('res.txt')
      os.unlink('tmp.txt')
      os.unlink('ghLOD.cmd')
    except:
      pass
  # now, we need to see how Linkage works with a set of p-values around DSL
  # DSL is global
  res = []
  for d in pop.dvars().DSL: 
    res.append( max(allPvalue[(d-2):(d+2)]))
  # use R to draw a picture
  r.postscript(file=epsFile, width=6, height=4)
  r.plot(allPvalue, main="-log10(P-value) at each marker (LOD method)", ylim=[0.01,5], 
    xlab="chromosome/markers", ylab="-log10 p-value", type='l', axes=False)
  r.box()
  r.abline( v = [pop.dvars().DSLafter[g]+pop.dvars().DSLdist[g] for g in range(len(pop.dvars().DSL))], lty=3)
  r.abline( h = cutoff )                       
  r.axis(1, [pop.dvars().numLoci*x for x in range(pop.numChrom())], [str(x+1) for x in range(pop.numChrom())])
  r.axis(2)
  r.dev_off()
  # try to get a jpg file
  try:
    if os.system("convert -rotate 90 %s %s " % (epsFile, jpgFile) ) == 0:
      return (2,res)  # success
    else:
      return (1,res) # fail
  except:
    return (1,res)  # fail
    
# create output directory if necessary
# a more friendly version of mkdir
def _mkdir(d):
  try:
    if not os.path.isdir(d):
      os.makedirs(d)
  except:
    print "Can not make output directory ", d
    sys.exit(1)

def popStat(pop, p, wt):
  ' calculate population statistics '
  # K -- populaiton prevalance
  print "Calculating population statistics "
  Stat(pop, numOfAffected=True)
  result = {}
  result[p+'_K'] = pop.dvars().numOfAffected * 1.0 / pop.popSize()
  # P11 = [ ] = proportion of 11 | affected, 
  # P12 = [ ] = proportion of 12 | affected
  DSL = pop.dvars().DSL
  P11 = [0.]*len(DSL)
  P12 = [0.]*len(DSL)
  P22 = [0.]*len(DSL)
  for ind in range(pop.popSize()):
    if pop.individual(ind).affected():
      for x in range(len(DSL)):
        s1 = pop.individual(ind).allele(DSL[x], 0)
        s2 = pop.individual(ind).allele(DSL[x], 1)
        if s1 == wt and s2 == wt:
          P11[x] += 1
        elif s1 == wt+1 and s2 == wt+1:
          P22[x] += 1
        else:
          P12[x] += 1
          
  N = pop.dvars().numOfAffected
  result[p+'_P11'] = [ x/N for x in P11 ]
  result[p+'_P12'] = [ x/N for x in P12 ]
  result[p+'_P22'] = [ x/N for x in P22 ]
  result[p+'_Fprime'] = [ (P12[x]/2. + P22[x])/N for x in range(len(DSL)) ]
  # Ks = Pr(Xs=1 | Xp=1 ) = Pr(Xs=1, Xp=1) | P(Xp=1)
  Xsp = 0.
  for ind in range(pop.popSize()/2):
    s1 = pop.individual(ind*2).affected()
    s2 = pop.individual(ind*2+1).affected()
    if s1 and s2:
      Xsp += 1
  result[p+'_Ks'] = 2*Xsp / pop.dvars().numOfAffected
  # Lambda = Ks/K
  result[p+'_Ls'] = result[p+'_Ks'] / result[p+'_K']
  return result
   
  
def analyzePopulation(dataset, peneFunc, penePara, wildtype, N, 
    numSample, outputDir, geneHunter, reAnalyzeOnly):
  '''
     this function organize all previous functions
     and
     1. Load a population
     2. apply different kinds of penetrance functions
     3. draw sample
     4. save samples
     5. apply TDT and/or Linkage method
     6. return a text summary and a result dictionary
  '''
  # get population
  logFile = dataset[0:-4] + ".log"
  # whether or not generate a new sample
  print "Loading dataset ", dataset
  pop = LoadPopulation(dataset)
  # log file is ...
  summary = '''\
    <h2>Dataset %s</h2>
    <h3>Log file (LD and other statistics): 
      <a href="%s">%s</a></h3>
    ''' % (dataset, logFile, logFile)
  #
  # actually write the log file in the summary page
  try:
    lf = open(logFile)
    summary += "<pre>\n"+lf.read()+"\n</pre>\n"
    lf.close()
  except:
    print "Can not open log file, ignoring. "
  #
  result = {
    'DSLafter':pop.dvars().DSLafter,
    'DSL':pop.dvars().DSL,
    'mu':pop.dvars().mutaRate, 
    'mi':pop.dvars().migrRate, 
    'rec':pop.dvars().recRate[0]}
  # save Fst, Het in res
  result['Fst'] = pop.dvars().AvgFst
  result['AvgHet'] = pop.dvars().AvgHetero
  result['alleleFreq'] = [1- pop.dvars().alleleFreq[i][wildtype] for i in pop.dvars().DSL]
  #
  # plot LD, res = 0, fail, 1: eps file, 2: converted to jpg
  epsFile = outputDir + "/LD_" + dataset + ".eps"
  jpgFile = outputDir + "/LD_" + dataset + ".jpg"
  
  # ldres has max D' on a chrom with DSL, and a chrom without DSL
  (suc,ldres) = plotLD(pop, epsFile, jpgFile)
  if suc > 0 : # eps file successfully generated
    summary += """<p>D' measures on two chromosomes with/without DSL at the last gen: 
    <a href="%s/LD_%s.eps">LD_%s.eps</a></p>\n""" % (outputDir, dataset, dataset)
  if suc > 1 : # jpg file is generated
    summary += '''<img src="%s/LD_%s.jpg"
      width=800, height=600>'''  % (outputDir, dataset)
  result['DpDSL'] = ldres['DpDSL']
  result['DpNon'] = ldres['DpNon']
  result['DDSL'] = ldres['DDSL']
  result['DNon'] = ldres['DNon']
  #
  # apply penetrance and get numSample for each sample
  summary += "<h3>Samples using different penetrance function</h3>\n"
  # now, deal with each penetrance ...
  for p in range(len(peneFunc)):
    summ = drawSamples(pop, 
      peneFunc[p], penePara[p], # penetrance and parameter
      wildtype, 
      numSample,    # number of sample for each setting
      saveFormat,   # save samples in which format
      outputDir,      # directory to save files
      reAnalyzeOnly # whether or not load sample directly
    )
    summary += summ
    # calculate population statistics like prevalence
    result.update( popStat(pop, peneFunc[p], wildtype) )
    if saveFormat == []:
      continue
    # for each sample
    for sn in range(numSample):
      print "Processing sample %s%d" % ( peneFunc[p], sn)
      # save these samples
      penDir = outputDir + "/" + peneFunc[p] + str(sn)
      relDir = '%s/%s%d/' % (outputDir, peneFunc[p], sn)
      _mkdir(penDir)

      # if there is a valid gene hunter program, run it
      (suc,res) = TDT(pop, geneHunter, -math.log10(0.05/pop.totNumLoci()), 
        penDir, "/Linkage/Aff", penDir + "/TDT.eps", penDir + "/TDT.jpg")
      #  if suc > 0 : # eps file succe
      if suc > 0 : # eps file successfully generated
        summary += """<h4>TDT analysis for affected sibpair data: 
          <a href="%s/TDT.eps">TDT.eps</a>""" % relDir
      if suc > 1 : # jpg file is generated
        summary += '''<p><img src="%s/TDT.jpg" width=800, height=600></p>''' % relDir
      # keep some numbers depending on the penetrance model
      result['TDT_%s_%d' % (peneFunc[p], sn)] = res
      # then the Linkage method
      (suc,res) = Linkage(pop, geneHunter, -math.log10(0.05/pop.totNumLoci()), 
        penDir, "/Linkage/Aff", penDir + "/LOD.eps", penDir + "/LOD.jpg")
      #  if suc > 0 : # eps file succe
      if suc > 0 : # eps file successfully generated
        summary += """<h4>LOD analysis for affected sibpair data:  <a href="%s/LOD.eps">LOD.eps</a>""" % relDir
      if suc > 1 : # jpg file is generated
        summary += '''<p><img src="%s/LOD.jpg" width=800, height=600></p>''' % relDir
      # keep some numbers depending on the penetrance model
      result['LOD_%s_%d' % (peneFunc[p], sn)] = res
  return (pop, summary, result)


if __name__ == '__main__':
  allParam = getOptions()
  # unpack options
  ( markerType, wildtype, dataset, saveFormat, peneFunc, 
    peneParaTmp, N, numSample, outputDir,
    geneHunter, reAnalyzeOnly) = allParam
  # load simuPOP libraries
  if markerType == 'microsatellite':
    simuOpt.setOptions(alleleType='short', quiet=True)
  else:
    simuOpt.setOptions(alleleType='binary', quiet=True)
  #
  from simuPOP import *
  from simuUtil import *
  # detect simuPOP version
  if simuRev() < 47:
    raise exceptions.SystemError('''This scripts requires simuPOP revision %d. 
      Please upgrade your simuPOP distribution.''' % simuRev() )
  #
  # if RPy is available, several figures will be drawn 
  try:
    from simuRPy import *
  except:
    hasRPy = False
  else:
    hasRPy = True
  #
  # check penePara
  if len(peneParaTmp) == 1:
    penePara = peneParaTmp*len(peneFunc)
  else:
    penePara = peneParaTmp
  if len(peneFunc) != len(penePara):
    raise exceptions.ValueError(
      "Please give penetrance parameter to each chosen penetrance function")
  # construct peneFunc and penePara in case that penePara is a list
  expandedPeneFunc = []
  expandedPenePara = []
  for p in range(len(peneFunc)):
    if type(penePara[p]) in [types.IntType, types.FloatType, types.LongType]:
      expandedPeneFunc.append( peneFunc[p])
      expandedPenePara.append( penePara[p])
    elif type(penePara[p]) in [types.TupleType, types.ListType]:
      for x in penePara[p]:
        expandedPeneFunc.append( peneFunc[p] + str(x) )
        expandedPenePara.append( x )
  #
  # outputDir should already exist
  (pop, text, res) =  analyzePopulation(dataset,
    expandedPeneFunc, expandedPenePara, wildtype, N, numSample, outputDir, 
    geneHunter, reAnalyzeOnly)
  #
  # write a report
  print "Writing a report (saved in summary.htm )"
  try:
    summary = open(outputDir + "/summary.htm", 'w')
  except:
    raise exceptions.IOError("Can not open a summary file : " + outputDir + "/summary.htm to write")
  summary.write('''
  <HTML>
  <HEAD>
  <TITLE>Summary of simulations</TITLE>
  <META NAME="description" CONTENT="summary of simulation">
  <META NAME="keywords" CONTENT="simuPOP">
  <META NAME="resource-type" CONTENT="document">
  <META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=iso-8859-1">
  </HEAD>
  <BODY >
  <h1>Output of %s</h1>
  <p><b>Time of simulation: </b> %s </p>
  <h2>Parameters </h2>
  <ul><pre>''' % (sys.argv[0], time.asctime()) )
  # write out parameters
  # start from options[1]
  simuOpt.printConfig(options[1:-2], allParam, summary )
  # a table built from res which has
  # idx, muta, migr, rec, af?, Fst, Het, TDT?
  summary.write('''
  </pre></ul>
  <h2>Summary of datasets </h2>
  ''')
  for i in range(len(res['DSL'])):
    summary.write('<th>allele Frq%d</th>'%(i+1))
  #
  # has TDT and some penetrance function
  summary.write('mu: %.5g<br>' % res['mu'])
  summary.write('mi: %.5g<br>' % res['mi'])
  summary.write('rec: %.5g<br>' % res['rec'])
  summary.write('Fst: %.3g<br>' % res['Fst'])
  summary.write('AvgHet: %.3g<br>' % res['AvgHet'])
  summary.write("D' (DSL)%.3g<br>" % res['DpDSL'])
  summary.write("D (DSL) %.3g<br>" % res['DDSL'])
  summary.write("D' (non-DSL) %.3g<br>" % res['DpNon'])
  summary.write('D (non-DSL) %.3g<br>' % res['DNon'])
  for i in range(len(res['DSL'])):
    summary.write('Allelefreq: %.3f<br>'% res['alleleFreq'][i] )
  # for each penetrance function
  if len(expandedPeneFunc) > 0:
    for p in expandedPeneFunc: # penetrance function
      summary.write("Penetrance function: %s<br>" % p )
      summary.write('K %.4g<br>' % res[p+'_K'])
      summary.write('Ks %.4g<br>' % res[p+'_Ks'])
      summary.write('Ls %.4g<br>' % res[p+'_Ls'])
      summary.write('P11: ' + ', '.join( ['%.4g'%x for x in res[p+'_P11'] ]) + '<br>')
      summary.write('P12: ' + ', '.join( ['%.4g'%x for x in res[p+'_P12'] ]) + '<br>')
      summary.write('P22: ' + ', '.join( ['%.4g'%x for x in res[p+'_P22'] ]) + '<br>')
      summary.write("F': " + ', '.join( ['%.4g'%x for x in res[p+'_Fprime'] ]) + '<br>')
      for met in ['TDT', 'LOD']:
        for num in range(numSample): # samples
          plusMinus = ''
          if not res.has_key(met+'_'+p+'_'+str(num)):
            continue
          for pvalue in res[met+'_'+p+'_'+str(num)]:
            if pvalue > -math.log10(0.05/(pop.numChrom()*pop.totNumLoci())):
              plusMinus += '+'
            else:
              plusMinus += '-'
          summary.write(''+plusMinus+'<br>')
  summary.write('''
   %s 
   <h2>Usage of %s</h2>
   <pre>%s </pre>
   </BODY></HTML>
   ''' % ( text, sys.argv[0], simuOpt.usage(options, __doc__)))
  summary.close()
  print "Done!"
