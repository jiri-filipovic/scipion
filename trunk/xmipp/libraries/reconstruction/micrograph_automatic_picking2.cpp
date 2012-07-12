/***************************************************************************
 *
 * Authors:    Carlos Oscar            coss@cnb.csic.es (2011)
 *
 * Unidad de  Bioinformatica of Centro Nacional de Biotecnologia , CSIC
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
 * 02111-1307  USA
 *
 *  All comments concerning this program package may be sent to the
 *  e-mail address 'xmipp@cnb.csic.es'
 ***************************************************************************/
#include <math.h>
#include "micrograph_automatic_picking2.h"
#include <data/filters.h>
#include <data/rotational_spectrum.h>
#include <reconstruction/denoise.h>
#include <data/xmipp_fft.h>
#include <data/xmipp_filename.h>
#include <algorithm>
#include <classification/uniform.h>


AutoParticlePicking2::AutoParticlePicking2(const FileName &fn, Micrograph *_m,int size,int filterNum,int pcaNum,int corrNum)
{
    __m = _m;
    fn_micrograph = fn;
    microImage.read(fn_micrograph);
    double t=std::max(0.25,50.0/size);
    scaleRate=std::min(1.0,t);
    particle_radius = (size*scaleRate)*0.5;
    particle_size = particle_radius*2;
    NRsteps=particle_size/2-3;
    filter_num = filterNum;
    corr_num = corrNum;
    num_correlation=filter_num+((filter_num-corr_num)*corr_num);
    NPCA = pcaNum;
}

//Generate filter bank from the micrograph image
void filterBankGenerator(MultidimArray<double> &inputMicrograph, const FileName &fnFilterBankStack, int filter_num)
{
    fnFilterBankStack.deleteFile();

    Image<double> Iaux;
    Iaux()=inputMicrograph;

    FourierFilter filter;
    filter.raised_w = 0.02;
    filter.FilterShape = RAISED_COSINE;
    filter.FilterBand = BANDPASS;
    MultidimArray< std::complex<double> > micrographFourier;
    FourierTransformer transformer;
    transformer.FourierTransform(Iaux(), micrographFourier, true);

    for (int i=0; i<filter_num; i++)
    {
        filter.w1 =0.025*i;
        filter.w2 = (filter.w1)+0.025;

        transformer.setFourier(micrographFourier);
        filter.applyMaskFourierSpace(inputMicrograph,transformer.fFourier);
        transformer.inverseFourierTransform();

        Iaux.write(fnFilterBankStack,i+1,true,WRITE_APPEND);
    }
}
void correlationBetweenPolarChannels(int n1, int n2, int nF,
                                     MultidimArray<double> &mIpolar, MultidimArray<double> &mIpolarCorr,
                                     CorrelationAux &aux)
{
    MultidimArray<double> imgPolar1, imgPolar2, imgPolarCorr, corr2D;
    imgPolar1.aliasImageInStack(mIpolar,n1);
    imgPolar2.aliasImageInStack(mIpolar,n2);

    imgPolarCorr.aliasImageInStack(mIpolarCorr,nF);
    correlation_matrix(imgPolar1,imgPolar2,corr2D,aux);
    imgPolarCorr=corr2D;
}

//To calculate the euclidean distance between to points
double euclidean_distance(const Particle2 &p1, const Particle2 &p2)
{
    double dx = (p1.x - p2.x);
    double dy = (p1.y - p2.y);
    return sqrt(dx * dx + dy * dy);
}

bool AutoParticlePicking2::checkDist(Particle2 &p)
{
    int num_part = __m->ParticleNo();
    int dist=0,min;
    Particle2 posSample;

    posSample.x=(__m->coord(0).X)*scaleRate;
    posSample.y=(__m->coord(0).Y)*scaleRate;
    min=euclidean_distance(p,posSample);
    for (int i=1;i<num_part;i++)
    {
        posSample.x=(__m->coord(i).X)*scaleRate;
        posSample.y=(__m->coord(i).Y)*scaleRate;
        dist=euclidean_distance(p,posSample);
        if (dist<min)
            min=dist;
    }

    if (min>(0.25*particle_radius))
        return true;
    else
        return false;
}

bool isLocalMaxima(MultidimArray<double> &inputArray,int x,int y)
{
    if (DIRECT_A2D_ELEM(inputArray,y-1,x-1)<DIRECT_A2D_ELEM(inputArray,y,x) &&
        DIRECT_A2D_ELEM(inputArray,y-1,x)<DIRECT_A2D_ELEM(inputArray,y,x) &&
        DIRECT_A2D_ELEM(inputArray,y-1,x+1)<DIRECT_A2D_ELEM(inputArray,y,x) &&
        DIRECT_A2D_ELEM(inputArray,y,x-1)<DIRECT_A2D_ELEM(inputArray,y,x) &&
        DIRECT_A2D_ELEM(inputArray,y,x+1)<DIRECT_A2D_ELEM(inputArray,y,x) &&
        DIRECT_A2D_ELEM(inputArray,y+1,x-1)<DIRECT_A2D_ELEM(inputArray,y,x) &&
        DIRECT_A2D_ELEM(inputArray,y+1,x)<DIRECT_A2D_ELEM(inputArray,y,x) &&
        DIRECT_A2D_ELEM(inputArray,y+1,x+1)<DIRECT_A2D_ELEM(inputArray,y,x))
        return true;
    else
        return false;
}

void  AutoParticlePicking2::polarCorrelation(MultidimArray<double> &Ipolar,MultidimArray<double> &IpolarCorr)
{
    int nF=NSIZE(Ipolar);
    CorrelationAux aux;

    for (int n=0; n<nF; ++n)
    {
        correlationBetweenPolarChannels(n,n,n,Ipolar,IpolarCorr,aux);
    }
    for (int i=0;i<(filter_num-corr_num);i++)
        for (int j=1;j<=corr_num;j++)
        {
            correlationBetweenPolarChannels(i,i+j,nF++,Ipolar,IpolarCorr,aux);
        }
}

AutoParticlePicking2::~AutoParticlePicking2()
{}

void AutoParticlePicking2::buildVector(MultidimArray<double> &inputVec,MultidimArray<double> &featureVec)
{
    MultidimArray<double> avg;
    MultidimArray<double> pcaBase;
    MultidimArray<double> vec;

    featureVec.resize(1,1,1,num_correlation*NPCA);
    for (int i=0;i<num_correlation;i++)
    {
        avg.aliasImageInStack(pcaModel,i*(NPCA+1));
        avg.resize(1,1,1,XSIZE(avg)*YSIZE(avg));
        vec.aliasImageInStack(inputVec,i);
        vec.resize(1,1,1,XSIZE(vec)*YSIZE(vec));
        vec-=avg;
        for (int j=0;j<NPCA;j++)
        {
            pcaBase.aliasImageInStack(pcaModel,(i*(NPCA+1)+1)+j);
            pcaBase.resize(1,1,1,XSIZE(pcaBase)*YSIZE(pcaBase));
            DIRECT_A1D_ELEM(featureVec,j+(i*NPCA))=PCAProject(pcaBase,vec);
        }
    }
}

void AutoParticlePicking2::buildInvariant(MultidimArray<double> &invariantChannel,int x,int y)
{
    MultidimArray<double>  pieceImage;
    MultidimArray<double> Ipolar;
    MultidimArray<double> mIpolar, filter;
    Ipolar.initZeros(filter_num,1,NangSteps,NRsteps);
    for (int j=0;j<filter_num;++j)
    {
        filter.aliasImageInStack(micrographStack(),j);
        extractParticle(x,y,filter,pieceImage);
        mIpolar.aliasImageInStack(Ipolar,j);
        convert2Polar(pieceImage,mIpolar);
    }
    polarCorrelation(Ipolar,invariantChannel);
}
double AutoParticlePicking2::PCAProject(MultidimArray<double> &pcaBasis,MultidimArray<double> &vec)
{
    double dotProduct=0;
    FOR_ALL_DIRECT_ELEMENTS_IN_ARRAY1D(pcaBasis)
    dotProduct += DIRECT_A1D_ELEM(pcaBasis,i) * DIRECT_A1D_ELEM(vec,i);
    return dotProduct;
}
void AutoParticlePicking2::trainPCA(const FileName &fnPositiveFeat)
{
    ImageGeneric positiveInvariant;
    MultidimArray<float> pcaVec;
    ArrayDim aDim;

    FileName fnPositiveInvariatn=fnPositiveFeat + "_invariant_Positive.stk";
    positiveInvariant.read(fnPositiveInvariatn, HEADER);
    positiveInvariant.getDimensions(aDim);
    int steps= aDim.ndim/num_correlation;
    for (int i=1;i<=num_correlation;i++)
    {
        for (int j=0;j<steps;j++)
        {
            positiveInvariant.readMapped(fnPositiveInvariatn,j*num_correlation+i);
            positiveInvariant().getImage(pcaVec);
            pcaVec.resize(1,1,1,XSIZE(pcaVec)*YSIZE(pcaVec));
            pcaAnalyzer.addVector(pcaVec);
        }
        pcaAnalyzer.subtractAvg();
        pcaAnalyzer.learnPCABasis(NPCA, 10);
        savePCAModel(fnPositiveFeat);
        pcaAnalyzer.clear();
    }
}
void AutoParticlePicking2::trainSVM(const FileName &fnModel,int numClassifier)
{
    if (numClassifier==1)
    {
        classifier.SVMTrain(dataSet,classLabel);
        classifier.SaveModel(fnModel);
    }
    else
    {
        classifier2.SVMTrain(dataSet1,classLabel1);
        classifier2.SaveModel(fnModel);
    }
}
int AutoParticlePicking2::automaticallySelectParticles()
{

    int endX,endY;
    double label,score;
    int gridStep=particle_radius/5;
    int size=XSIZE(microImage());
    Particle2 p;
    MultidimArray<double> IpolarCorr;
    MultidimArray<double> featVec;
    MultidimArray<double> convolveRes;
    MultidimArray<int> mask;
    CorrelationAux aux;
    FourierFilter filter;

    IpolarCorr.initZeros(num_correlation,1,NangSteps,NRsteps);
    endX=XSIZE(microImage())-particle_radius;
    endY=YSIZE(microImage())-particle_radius;
    //Generating Mask
    mask.resize(particleAvg);
    mask.setXmippOrigin();
    BinaryCircularMask(mask,XSIZE(particleAvg)/2);
    normalize_NewXmipp(particleAvg,mask);
    particleAvg.setXmippOrigin();
    particleAvg.selfWindow(FIRST_XMIPP_INDEX(size),FIRST_XMIPP_INDEX(size),LAST_XMIPP_INDEX(size),LAST_XMIPP_INDEX(size));
    correlation_matrix(microImage(),particleAvg,convolveRes,aux);
    filter.raised_w = 0.02;
    filter.FilterShape = RAISED_COSINE;
    filter.FilterBand = BANDPASS;
    filter.w1 =1.0/double(particle_size);
    filter.w2 =1.0/(double(particle_size)/3);
    filter.applyMaskSpace(convolveRes);
    std::ofstream fh_training;
    fh_training.open("particles_cord1.txt");
    for (int i=particle_radius;i<endY;i++)
        for (int j=particle_radius;j<endX;j++)
        {
            if (isLocalMaxima(convolveRes,j,i))
            {
                buildInvariant(IpolarCorr,j,i);
                buildVector(IpolarCorr,featVec);
                double max=featVec.computeMax();
                double min=featVec.computeMin();
                FOR_ALL_DIRECT_ELEMENTS_IN_ARRAY1D(featVec)
                DIRECT_A1D_ELEM(featVec,i)=-1+((2)*((DIRECT_A1D_ELEM(featVec,i)-min)/(max-min)));
                label=classifier.predict(featVec,score);
                if (label==1)
                {
                    if (classifier2.getNumClasses()==2)
                    {
                        label=classifier2.predict(featVec,score);
                        if (label==1)
                        {
                            p.x=j;
                            p.y=i;
                            p.status=1;
                            p.cost=score;
                            p.vec=featVec;
                            auto_candidates.push_back(p);
                        }
                    }
                    else
                    {
                        p.x=j;
                        p.y=i;
                        p.status=1;
                        p.cost=score;
                        p.vec=featVec;
                        auto_candidates.push_back(p);
                    }

                }
            }
        }
    // Remove the occluded particles
    std::cerr<<auto_candidates.size()<<std::endl;
    for (int i=0;i<auto_candidates.size();++i)
        for (int j=0;j<auto_candidates.size()-i-1;j++)
            if (auto_candidates[j].cost<auto_candidates[j+1].cost)
            {
                p=auto_candidates[j+1];
                auto_candidates[j+1]=auto_candidates[j];
                auto_candidates[j]=p;
            }
    std::cerr<<"Sorting is Done!!!"<<std::endl;
    for (int i=0;i<auto_candidates.size()-1;++i)
    {
        if (auto_candidates[i].status==-1)
            continue;
        p=auto_candidates[i];
        for (int j=i+1;j<auto_candidates.size();j++)
        {
            if (auto_candidates[j].x>p.x-particle_radius && auto_candidates[j].x<p.x+particle_radius
                && auto_candidates[j].y>p.y-particle_radius && auto_candidates[j].y<p.y+particle_radius)
            {
                if (p.cost<auto_candidates[j].cost)
                {
                    auto_candidates[i].status=-1;
                    p=auto_candidates[j];
                }
                else
                    auto_candidates[j].status=-1;
            }
        }
    }
    std::cerr<<"Ocllusion is resolved!!!"<<std::endl;
//    for (int i=0;i<auto_candidates.size();++i)
//    {
//        if (auto_candidates[i].status!=-1)
//            fh_training<<auto_candidates[i].x<<" "<<auto_candidates[i].y<<std::endl;
//    }
//    //std::cerr<<auto_candidates[i].cost<<std::endl;

    //fh_training.close();
    return auto_candidates.size();
}
void AutoParticlePicking2::add2Dataset(const FileName &fn_Invariant,int label)
{
    ImageGeneric positiveInvariant;
    MultidimArray<double> vec;
    MultidimArray<double> avg;
    MultidimArray<double> pcaBase;
    FourierFilter filter;
    ArrayDim aDim;
    int yDataSet=YSIZE(dataSet);

    positiveInvariant.read(fn_Invariant, HEADER);
    positiveInvariant.getDimensions(aDim);
    int steps= aDim.ndim/num_correlation;
    dataSet.resize(1,1,yDataSet+steps,num_correlation*NPCA);
    classLabel.resize(1,1,1,YSIZE(dataSet));
    for (int n=yDataSet;n<XSIZE(classLabel);n++)
        classLabel(n)=label;
    for (int i=0;i<num_correlation;i++)
    {
        avg.aliasImageInStack(pcaModel,i*(NPCA+1));
        avg.resize(1,1,1,XSIZE(avg)*YSIZE(avg));
        for (int j=0;j<NPCA;j++)
        {
            pcaBase.aliasImageInStack(pcaModel,i*(NPCA+1)+1+j);
            pcaBase.resize(1,1,1,XSIZE(pcaBase)*YSIZE(pcaBase));
            for (int k=0;k<steps;k++)
            {
                positiveInvariant.readMapped(fn_Invariant,k*num_correlation+i+1);
                positiveInvariant().getImage(vec);
                vec.resize(1,1,1,XSIZE(vec)*YSIZE(vec));
                vec-=avg;
                DIRECT_A2D_ELEM(dataSet,k+yDataSet,j+(i*NPCA))=PCAProject(pcaBase,vec);
            }
        }
    }
    fn_Invariant.deleteFile();
}

void AutoParticlePicking2::add2Dataset()
{
    int yDataSet=YSIZE(dataSet);
    dataSet.resize(1,1,yDataSet+auto_candidates.size(),num_correlation*NPCA);
    classLabel.resize(1,1,1,YSIZE(dataSet));
    for (int n=yDataSet;n<XSIZE(classLabel);n++)
        classLabel(n)=3;
    for (int i=0;i<auto_candidates.size();i++)
    {
        for (int j=0;j<XSIZE(dataSet);j++)
        {
            DIRECT_A2D_ELEM(dataSet,i+yDataSet,j)=DIRECT_A1D_ELEM(auto_candidates[i].vec,j);
        }
    }
}

void AutoParticlePicking2::extractPositiveInvariant(const FileName &fnInvariantFeat)
{

    MultidimArray<double> IpolarCorr;
    MultidimArray<double>  pieceImage;
    int num_part = __m->ParticleNo();
    Image<double> II;
    FileName fnPositiveInvariatn=fnInvariantFeat+"_Positive.stk";
    IpolarCorr.initZeros(num_correlation,1,NangSteps,NRsteps);

    for (int i=0;i<num_part;i++)
    {
        int x = (__m->coord(i).X)*scaleRate;
        int y = (__m->coord(i).Y)*scaleRate;

        buildInvariant(IpolarCorr,x,y);
        extractParticle(x,y,microImage(),pieceImage);
        pieceImage.setXmippOrigin();
        particleAvg.setXmippOrigin();
        particleAvg=particleAvg+pieceImage;
        II() = IpolarCorr;
        II.write(fnPositiveInvariatn,ALL_IMAGES,true,WRITE_APPEND);
    }
    particleAvg/=num_part;
}

void AutoParticlePicking2::extractNegativeInvariant(const FileName &fnInvariantFeat)
{
    MultidimArray<double> IpolarCorr;
    MultidimArray<double> randomValues;
    MultidimArray<int> randomIndexes;
    std::vector<Particle2> negativeSamples;

    int num_part = __m->ParticleNo();
    Image<double> II;
    FileName fnNegativeInvariatn=fnInvariantFeat+"_Negative.stk";
    IpolarCorr.initZeros(num_correlation,1,NangSteps,NRsteps);
    extractNonParticle(negativeSamples);
    // Choose some random non-particles
    RandomUniformGenerator<double> randNum(0,1);
    randomValues.resize(1,1,1,negativeSamples.size());
    FOR_ALL_DIRECT_ELEMENTS_IN_ARRAY1D(randomValues)
    DIRECT_A1D_ELEM(randomValues,i)=randNum();
    randomValues.indexSort(randomIndexes);
    int numNegatives;
    if (num_part<40)
        numNegatives=40;
    else
        numNegatives=num_part*2;
    for (int i=0;i<numNegatives;i++)
    {
        int x = negativeSamples[DIRECT_A1D_ELEM(randomIndexes,i)].x;
        int y = negativeSamples[DIRECT_A1D_ELEM(randomIndexes,i)].y;
        buildInvariant(IpolarCorr,x,y);
        II() = IpolarCorr;
        II.write(fnNegativeInvariatn,ALL_IMAGES,true,WRITE_APPEND);
    }
}

void AutoParticlePicking2::extractInvariant(const FileName &fnInvariantFeat)
{
    extractPositiveInvariant(fnInvariantFeat);
    extractNegativeInvariant(fnInvariantFeat);
}

void AutoParticlePicking2::extractParticle(const int x, const int y, MultidimArray<double> &filter,
        MultidimArray<double> &particleImage)
{
    int startX, startY, endX, endY;
    startX=x-particle_radius;
    startY=y-particle_radius;
    endX=x+particle_radius;
    endY=y+particle_radius;

    filter.window(particleImage,startY,startX,endY,endX);
    normalize_OldXmipp(particleImage);
}

void AutoParticlePicking2::extractNonParticle(std::vector<Particle2> &negativePosition)
{
    int endX, endY;
    int gridStep=particle_radius/2;
    Particle2 negSample;
    endX=XSIZE(microImage())-particle_radius;
    endY=YSIZE(microImage())-particle_radius;

    for (int i=particle_radius;i<endY;i=i+gridStep)
        for (int j=particle_radius;j<endX;j=j+gridStep)
        {
            negSample.y=i;
            negSample.x=j;
            if (checkDist(negSample))
            {
                negativePosition.push_back(negSample);
            }
        }
}
void AutoParticlePicking2::convert2Polar(MultidimArray<double> &particleImage, MultidimArray<double> &polar)
{
    Matrix1D<double> R;
    particleImage.setXmippOrigin();
    image_convertCartesianToPolar_ZoomAtCenter(particleImage,polar,
            R,1,3,XSIZE(particleImage)/2,NRsteps,0,2*PI,NangSteps);
}

void AutoParticlePicking2::loadTrainingSet(const FileName &fn)
{
    int x,y;
    String dummy;
    std::ifstream fhTrain;
    fhTrain.open(fn.c_str());
    fhTrain>>y>>x;
    dataSet.resize(1,1,y,x);
    classLabel.resize(1,1,1,y);
    for (int i=0;i<y;i++)
    {
        fhTrain>>classLabel(i);
        for (int j=0;j<x;j++)
            fhTrain>>DIRECT_A2D_ELEM(dataSet,i,j);
    }
    fhTrain.close();
}

void AutoParticlePicking2::saveTrainingSet(const FileName &fn)
{
    std::ofstream fhTrain;
    fhTrain.open(fn.c_str());
    fhTrain<<YSIZE(dataSet)<<" "<<XSIZE(dataSet)<<std::endl;
    for (int i=0;i<YSIZE(dataSet);i++)
    {
        fhTrain<<classLabel(i)<<std::endl;
        for (int j=0;j<XSIZE(dataSet);j++)
            fhTrain<<DIRECT_A2D_ELEM(dataSet,i,j)<<" ";
        fhTrain<<std::endl;
    }
    fhTrain.close();
}

void AutoParticlePicking2::savePCAModel(const FileName &fn_root)
{
    FileName fnPcaModel=fn_root + "_pca_model.stk";
    Image<double> II;
    MultidimArray<double> avg;

    avg=pcaAnalyzer.avg;
    avg.resize(1,1,NangSteps,NRsteps);
    II()=avg;
    II.write(fnPcaModel,ALL_IMAGES,true,WRITE_APPEND);
    for (int i=0;i<NPCA;i++)
    {
        MultidimArray<double> pcaBasis;
        pcaBasis=pcaAnalyzer.PCAbasis[i];
        pcaBasis.resize(1,1,NangSteps,NRsteps);
        II()=pcaBasis;
        II.write(fnPcaModel,ALL_IMAGES,true,WRITE_APPEND);
    }
}

/* Save particles ---------------------------------------------------------- */
int AutoParticlePicking2::saveAutoParticles(const FileName &fn) const
{
    MetaData MD;
    size_t nmax = auto_candidates.size();
    for (size_t n = 0; n < nmax; ++n)
    {
        const Particle2 &p= auto_candidates[n];
        if (p.cost>0 && p.status==1)
        {
            size_t id = MD.addObject();
            MD.setValue(MDL_XCOOR, int(p.x*(1.0/scaleRate)), id);
            MD.setValue(MDL_YCOOR, int(p.y*(1.0/scaleRate)), id);
            MD.setValue(MDL_COST, p.cost, id);
            MD.setValue(MDL_ENABLED,1,id);
        }
    }
    MD.write(fn,MD_OVERWRITE);
    return MD.size();
}

/* Save features of Autoparticles ---------------------------------------------------------- */
void AutoParticlePicking2::saveAutoVectors(const FileName &fn)
{
    std::ofstream fhVectors;
    fhVectors.open(fn.c_str());
    int X=XSIZE(auto_candidates[0].vec);
    fhVectors<<auto_candidates.size()<<" "<<X<<std::endl;
    size_t nmax = auto_candidates.size();
    for (size_t n = 0; n < nmax; ++n)
    {
        const Particle2 &p= auto_candidates[n];
        if (p.cost>0 && p.status==1)
        {
            for (int j=0;j<X;++j)
            {
                fhVectors<<DIRECT_A1D_ELEM(p.vec,j)<<" ";
            }
            fhVectors<<std::endl;
        }
    }
    fhVectors.close();
}

/* Load features of Autoparticles ---------------------------------------------------------- */
void AutoParticlePicking2::loadAutoVectors(const FileName &fn)
{
    int numVector;
    int numFeature;
    std::ifstream fhVectors;
    fhVectors.open(fn.c_str());
    fhVectors>>numVector>>numFeature;
    for (int n = 0;n<numVector;++n)
    {
        Particle2 p;
        p.vec.resize(1,1,1,numFeature);
        for (int j=0;j<numFeature;++j)
            fhVectors>>DIRECT_A1D_ELEM(p.vec,j);
        auto_candidates.push_back(p);
    }
    fhVectors.close();
}

/* Save features of rejected particles ---------------------------------------------------------- */
void AutoParticlePicking2::saveRejectedVectors(const FileName &fn)
{
    std::ofstream fhVectors;
    fhVectors.open(fn.c_str());
    int X=XSIZE(rejected_particles[0].vec);
    fhVectors<<rejected_particles.size()<<" "<<X<<std::endl;
    size_t nmax = rejected_particles.size();
    for (size_t n = 0; n < nmax; ++n)
    {
        const Particle2 &p= rejected_particles[n];
        for (int j=0;j<X;++j)
        {
            fhVectors<<DIRECT_A1D_ELEM(p.vec,j)<<" ";
        }
        fhVectors<<std::endl;
    }
    fhVectors.close();
}

void AutoParticlePicking2::generateTrainSet()
{
    int cnt=0;
    FOR_ALL_DIRECT_ELEMENTS_IN_ARRAY1D(classLabel)
    if (DIRECT_A1D_ELEM(classLabel,i)==1 || DIRECT_A1D_ELEM(classLabel,i)==3)
        cnt++;
    dataSet1.resize(1,1,cnt,XSIZE(dataSet));
    classLabel1.resize(1,1,1,cnt);
    cnt=0;
    FOR_ALL_DIRECT_ELEMENTS_IN_ARRAY1D(classLabel)
    if (DIRECT_A1D_ELEM(classLabel,i)==1 || DIRECT_A1D_ELEM(classLabel,i)==3)
    {
        for (int j=0;j<XSIZE(dataSet);j++)
        {
            DIRECT_A2D_ELEM(dataSet1,cnt,j)=DIRECT_A2D_ELEM(dataSet,i,j);
        }
        if (DIRECT_A1D_ELEM(classLabel,i)==3)
        {
            DIRECT_A1D_ELEM(classLabel1,cnt)=2;
            DIRECT_A1D_ELEM(classLabel,i)=2;
        }
        else
            DIRECT_A1D_ELEM(classLabel1,cnt)=1;

        cnt++;
    }

}

void AutoParticlePicking2::normalizeDataset(int a,int b)
{
    double max,min;
    MultidimArray<double> maxA,minA;
    //    maxA.resize(1,1,1,XSIZE(dataSet));
    //    minA.resize(1,1,1,XSIZE(dataSet));
    //    for (int i=0;i<XSIZE(dataSet);i++)
    //    {
    //        max=min=DIRECT_A2D_ELEM(dataSet,0,i);
    //        for (int j=1;j<YSIZE(dataSet);j++)
    //        {
    //            if (max<DIRECT_A2D_ELEM(dataSet,j,i))
    //                max=DIRECT_A2D_ELEM(dataSet,j,i);
    //            if (min>DIRECT_A2D_ELEM(dataSet,j,i))
    //                min=DIRECT_A2D_ELEM(dataSet,j,i);
    //        }
    //        DIRECT_A1D_ELEM(maxA,i)=max;
    //        DIRECT_A1D_ELEM(minA,i)=min;
    //    }
    //    for (int i=0;i<YSIZE(dataSet);i++)
    //    {
    //     for (int j=0;j<XSIZE(dataSet);j++)
    //     {
    //      max=DIRECT_A1D_ELEM(maxA,j);
    //      min=DIRECT_A1D_ELEM(minA,j);
    //      DIRECT_A2D_ELEM(dataSet,i,j)=a+((b-a)*((DIRECT_A2D_ELEM(dataSet,i,j)-min)/(max-min)));
    //     }
    //    }
    maxA.resize(1,1,1,YSIZE(dataSet));
    minA.resize(1,1,1,YSIZE(dataSet));
    for (int i=0;i<YSIZE(dataSet);i++)
    {
        max=min=DIRECT_A2D_ELEM(dataSet,i,0);
        for (int j=1;j<XSIZE(dataSet);j++)
        {
            if (max<DIRECT_A2D_ELEM(dataSet,i,j))
                max=DIRECT_A2D_ELEM(dataSet,i,j);
            if (min>DIRECT_A2D_ELEM(dataSet,i,j))
                min=DIRECT_A2D_ELEM(dataSet,i,j);
        }
        DIRECT_A1D_ELEM(maxA,i)=max;
        DIRECT_A1D_ELEM(minA,i)=min;
    }
    for (int i=0;i<YSIZE(dataSet);i++)
    {
        max=DIRECT_A1D_ELEM(maxA,i);
        min=DIRECT_A1D_ELEM(minA,i);
        for (int j=0;j<XSIZE(dataSet);j++)
            DIRECT_A2D_ELEM(dataSet,i,j)=a+((b-a)*((DIRECT_A2D_ELEM(dataSet,i,j)-min)/(max-min)));
    }
}

// ==========================================================================
// Section: Program interface ===============================================
// ==========================================================================
void ProgMicrographAutomaticPicking2::readParams()
{
    fn_micrograph = getParam("-i");
    fn_model = getParam("--model");
    size = getIntParam("--particleSize");
    mode = getParam("--mode");
    if (mode == "buildinv")
    {
        fn_train = getParam("--mode", 1);
    }
    NPCA = getIntParam("--NPCA");
    filter_num = getIntParam("--filter_num");
    corr_num = getIntParam("--NCORR");
    Nthreads = getIntParam("--thr");
    fn_root = getParam("--outputRoot");
    fast = checkParam("--fast");
    incore = checkParam("--in_core");
}

void ProgMicrographAutomaticPicking2::defineParams()
{
    addUsageLine("Automatic particle picking for micrographs");
    addUsageLine("+The algorithm is designed to learn the particles from the user, as well as from its own errors.");
    addUsageLine("+The algorithm is fully described in [[http://www.ncbi.nlm.nih.gov/pubmed/19555764][this paper]].");
    addParamsLine("  -i <micrograph>               : Micrograph image");
    addParamsLine("  --outputRoot <rootname>       : Output rootname");
    addParamsLine("  --mode <mode>                 : Operation mode");
    addParamsLine("         where <mode>");
    addParamsLine("                    try              : Try to autoselect within the training phase.");
    addParamsLine("                    train            : Train the classifier using the invariants features.");
    addParamsLine("                                     : <rootname>_auto_feature_vectors.txt contains the particle structure created by this program when used in automatic selection mode");
    addParamsLine("                                     : <rootname>_false_positives.xmd contains the list of false positives among the automatically picked particles");
    addParamsLine("                    autoselect  : Autoselect");
    addParamsLine("                    buildinv <posfile=\"\"> : posfile contains the coordinates of manually picked particles");
    addParamsLine("  --model <model_rootname>      : Bayesian model of the particles to pick");
    addParamsLine("  --particleSize <size>         : Particle size in pixels");
    addParamsLine("  [--thr <p=1>]                 : Number of threads for automatic picking");
    addParamsLine("  [--fast]                      : Perform a fast preprocessing of the micrograph (Fourier filter instead of Wavelet filter)");
    addParamsLine("  [--in_core]                   : Read the micrograph in memory");
    addParamsLine("  [--filter_num <n=6>]          : The number of filters in filter bank");
    addParamsLine("  [--NPCA <n=4>]               : The number of PCA components");
    addParamsLine("  [--NCORR <n=2>]               : The number of PCA components");
    addExampleLine("Automatically select particles during training:", false);
    addExampleLine("xmipp_micrograph_automatic_picking -i micrograph.tif --particleSize 100 --model model --thr 4 --outputRoot micrograph --mode try ");
    addExampleLine("Training:", false);
    addExampleLine("xmipp_micrograph_automatic_picking -i micrograph.tif --particleSize 100 --model model --thr 4 --outputRoot micrograph --mode train manual.pos");
    addExampleLine("Automatically select particles after training:", false);
    addExampleLine("xmipp_micrograph_automatic_picking -i micrograph.tif --particleSize 100 --model model --thr 4 --outputRoot micrograph --mode autoselect");
}

void ProgMicrographAutomaticPicking2::run()
{
    Micrograph m;
    m.open_micrograph(fn_micrograph);

    FileName fnFilterBank=fn_root+"_filterbank.stk";
    FileName familyName=fn_model.removeDirectories();
    FileName fnAutoParticles=familyName+"@"+fn_root+"_auto.pos";
    FileName fnInvariant=fn_model + "_invariant";
    FileName fnPCAModel=fn_model + "_pca_model.stk";
    FileName fnSVMModel= fn_model + "_svm.txt";
    FileName fnSVMModel2= fn_model + "_svm2.txt";
    FileName fnVector= fn_model + "_training.txt";
    FileName fnAutoVectors= fn_model + "_auto_vector.txt";
    FileName fnRejectedVectors= fn_model + "_rejected_vector.txt";
    FileName fnAvgModel= fn_model + "_particle_avg.xmp";
    AutoParticlePicking2 *autoPicking = new AutoParticlePicking2(fn_micrograph,&m,size,filter_num,NPCA,corr_num);

    if (mode !="train")
    {
        // Resize the Micrograph
        selfScaleToSizeFourier((m.Ydim)*autoPicking->scaleRate,(m.Xdim)*autoPicking->scaleRate,autoPicking->microImage(), 2);
        // Generating the filter bank
        filterBankGenerator(autoPicking->microImage(), fnFilterBank, filter_num);
        autoPicking->micrographStack.read(fnFilterBank, DATA);
    }

    if (mode == "buildinv")
    {
        MetaData MD;
        // Insert all true positives
        if (fn_train!="")
        {
            MD.read(fn_train);
            int x, y;
            FOR_ALL_OBJECTS_IN_METADATA(MD)
            {
                MD.getValue(MDL_XCOOR, x, __iter.objId);
                MD.getValue(MDL_YCOOR, y, __iter.objId);
                m.add_coord(x, y, 0, 1);
            }
            // Insert the false positives
            if (fnAutoParticles.existsTrim())
            {
                int idx=0;
                MD.read(fnAutoParticles);
                if (MD.size() > 0)
                {
                    autoPicking->loadAutoVectors(fnAutoVectors);
                    FOR_ALL_OBJECTS_IN_METADATA(MD)
                    {
                        int enabled;
                        MD.getValue(MDL_ENABLED,enabled,__iter.objId);
                        if (enabled==-1)
                            autoPicking->rejected_particles.push_back(autoPicking->auto_candidates[idx]);
                        else
                        {
                            MD.getValue(MDL_XCOOR, x, __iter.objId);
                            MD.getValue(MDL_YCOOR, y, __iter.objId);
                            m.add_coord(x, y, 0, 1);
                        }
                        ++idx;
                    }
                }
                autoPicking->saveRejectedVectors(fnRejectedVectors);
            }
        }
        if (fnAvgModel.exists())
        {
            Image<double> II;
            II.read(fnAvgModel);
            autoPicking->particleAvg=II();
        }
        else
        {
            autoPicking->particleAvg.initZeros(autoPicking->particle_size+1,autoPicking->particle_size+1);
            autoPicking->particleAvg.setXmippOrigin();
        }
        autoPicking->extractInvariant(fnInvariant);
        Image<double> II;
        II() = autoPicking->particleAvg;
        II.write(fnAvgModel);
    }

    if (mode == "try" || mode == "autoselect")
    {
        autoPicking->micrographStack.read(fnFilterBank, DATA);
        // Read the PCA Model
        Image<double> II;
        II.read(fnPCAModel);
        autoPicking->pcaModel=II();
        // Read the SVM model
        autoPicking->classifier.LoadModel(fnSVMModel);
        autoPicking->classifier2.LoadModel(fnSVMModel2);
        // Read the average of the particles for convolution
        II.read(fnAvgModel);
        autoPicking->particleAvg=II();
        int num=autoPicking->automaticallySelectParticles();
        autoPicking->saveAutoParticles(fnAutoParticles);
        std::cerr<<"The positions are saved!!!";
        if (mode == "try")
            autoPicking->saveAutoVectors(fnAutoVectors);
        std::cerr<<"The vectors are saved!!!";
    }
    if (mode == "train")
    {
        if (!fnPCAModel.exists())
            autoPicking->trainPCA(fn_root);
        Image<double> II;
        II.read(fnPCAModel);
        autoPicking->pcaModel=II();
        if (fnVector.exists())
            autoPicking->loadTrainingSet(fnVector);
        autoPicking->add2Dataset(fnInvariant+"_Positive.stk",1);
        autoPicking->add2Dataset(fnInvariant+"_Negative.stk",2);
        if (fnRejectedVectors.exists())
        {
            autoPicking->loadAutoVectors(fnRejectedVectors);
            autoPicking->add2Dataset();
        }
        autoPicking->normalizeDataset(-1,1);
        autoPicking->saveTrainingSet(fnVector);
        autoPicking->generateTrainSet();
        autoPicking->trainSVM(fnSVMModel,1);
        autoPicking->trainSVM(fnSVMModel2,2);
    }
}


