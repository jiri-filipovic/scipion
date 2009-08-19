/***************************************************************************
 *
 * Authors: Sjors Scheres (scheres@cnb.uam.es)
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
 *  e-mail address 'xmipp@cnb.uam.es'
 ***************************************************************************/

#include <mpi.h>

#include <reconstruction/ml_align2d.h>
#define TAG_DOCFILE 12
#define TAG_DOCFILESIZE 13
 
int main(int argc, char **argv)
{
    Prog_MLalign2D_prm prm;

    int c, nn, imgno, opt_refno, iaux;
    double LL, sumw_allrefs, convv, sumcorr, new_resol;
    std::vector<double> conv;
    double aux, wsum_sigma_noise, wsum_sigma_offset;
    std::vector<Matrix2D<double > > wsum_Mref;
    std::vector<double> sumw, sumw2, sumwsc, sumwsc2, sumw_mirror;
    Matrix2D<double> Maux;
    Matrix1D<double> Vaux;
    FileName fn_img;
    DocFile DFo;
    // For parallelization
    int rank, size, num_img_tot;
    bool converged;

    // Init Parallel interface
    MPI_Init(&argc, &argv);
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &size);
    MPI_Status status;

    // Get input parameters
    try
    {

        // Read subsequently to avoid problems in restart procedure
        for (int proc = 0; proc < size; proc++)
        {
            if (proc == rank) prm.read(argc, argv);
            MPI_Barrier(MPI_COMM_WORLD);
        }
        if (rank != 0) prm.verb = 0;

        // All nodes produce general side-info
        prm.produceSideInfo();

        // Some output to screen
        if (rank == 0) prm.show();

        // Create references from random subset averages, or read them from selfile
        if (prm.fn_ref == "")
        {
            if (prm.n_ref != 0)
            {
                if (rank == 0)
                {
                    prm.generateInitialReferences();
                }
                else
                {
                    prm.fn_ref = prm.fn_root + "_it";
                    prm.fn_ref.compose(prm.fn_ref, 0, "sel");
                }
                MPI_Barrier(MPI_COMM_WORLD);
            }
            else
            {
                REPORT_ERROR(1, "Please provide -ref or -nref");
            }
        }
        MPI_Barrier(MPI_COMM_WORLD);

        // Select only relevant part of selfile for this rank
        prm.SF.mpi_select_part(rank, size, num_img_tot);

        // And produce selfile-specific side-info
        prm.produceSideInfo2();
        MPI_Barrier(MPI_COMM_WORLD);

    }
    catch (Xmipp_error XE)
    {
        if (rank == 0)
        {
            std::cout << XE;
            prm.usage();
        }
        MPI_Finalize();
        exit(1);
    }

    try
    {
        Maux.resize(prm.oridim, prm.oridim);
        Maux.setXmippOrigin();

        // Loop over all iterations
        for (int iter = prm.istart; iter <= prm.Niter; iter++)
        {
            if (prm.verb > 0) std::cerr << "  Multi-reference refinement:  iteration " << iter << " of " << prm.Niter << std::endl;

            // Save old reference images
            for (int refno = 0;refno < prm.n_ref; refno++) prm.Iold[refno]() = prm.Iref[refno]();

            // Integrate over all images
            prm.expectation(prm.SF, prm.Iref, iter,
                            LL, sumcorr, DFo, wsum_Mref,
                            wsum_sigma_noise, wsum_sigma_offset, 
                            sumw,  sumw2, sumwsc, sumwsc2, sumw_mirror);

            // Here MPI_allreduce of all wsums,LL and sumcorr !!!
            MPI_Allreduce(&LL, &aux, 1, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
            LL = aux;
            MPI_Allreduce(&sumcorr, &aux, 1, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
            sumcorr = aux;
            MPI_Allreduce(&wsum_sigma_noise, &aux, 1, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
            wsum_sigma_noise = aux;
            MPI_Allreduce(&wsum_sigma_offset, &aux, 1, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
            wsum_sigma_offset = aux;
            for (int refno = 0; refno < prm.n_ref; refno++)
            {
                if (prm.do_frc)
                {
                    MPI_Allreduce(MULTIDIM_ARRAY(wsum_Mref[2*refno]), MULTIDIM_ARRAY(Maux),
                                  MULTIDIM_SIZE(wsum_Mref[2*refno]), MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
                    wsum_Mref[2*refno] = Maux;
                    MPI_Allreduce(MULTIDIM_ARRAY(wsum_Mref[2*refno+1]), MULTIDIM_ARRAY(Maux),
                                  MULTIDIM_SIZE(wsum_Mref[2*refno+1]), MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
                    wsum_Mref[2*refno+1] = Maux;
                    MPI_Allreduce(&sumw[2*refno], &aux, 1, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
                    sumw[2*refno] = aux;
                    MPI_Allreduce(&sumw[2*refno+1], &aux, 1, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
                    sumw[2*refno+1] = aux;
                    MPI_Allreduce(&sumwsc2[2*refno], &aux, 1, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
                    sumwsc2[2*refno] = aux;
                    MPI_Allreduce(&sumwsc2[2*refno+1], &aux, 1, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
                    sumwsc2[2*refno+1] = aux;
                }
                else
                {
                    MPI_Allreduce(MULTIDIM_ARRAY(wsum_Mref[refno]), MULTIDIM_ARRAY(Maux),
                                  MULTIDIM_SIZE(wsum_Mref[refno]), MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
                    wsum_Mref[refno] = Maux;
                    MPI_Allreduce(&sumw[refno], &aux, 1, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
                    sumw[refno] = aux;
                    MPI_Allreduce(&sumwsc2[refno], &aux, 1, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
                    sumwsc2[refno] = aux;
                }
                MPI_Allreduce(&sumw_mirror[refno], &aux, 1, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
                sumw_mirror[refno] = aux;
                MPI_Allreduce(&sumw2[refno], &aux, 1, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
                sumw2[refno] = aux;
                MPI_Allreduce(&sumwsc[refno], &aux, 1, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
                sumwsc[refno] = aux;
            }

            // Update model parameters
            prm.maximization(wsum_Mref, wsum_sigma_noise, wsum_sigma_offset, 
                             sumw, sumw2, sumwsc, sumwsc2, sumw_mirror, 
                             sumcorr, sumw_allrefs);

            // Check convergence
            converged = prm.checkConvergence(conv);

            // Calculate resolution (and update)
            if (prm.do_frc)
                new_resol = prm.calculateResolution(iter);
            if (prm.do_multires)
                if (prm.changeCurrentResolution(new_resol))
                    converged = false;

            // Write intermediate files 
            if (rank != 0)
            {
                // All slaves send docfile to the master
                std::ostringstream doc;
                doc << DFo;
                int s_size=  doc.str().size();
                char results[s_size];
                strncpy(results,doc.str().c_str(),s_size);
                results[s_size]='\0';
                MPI_Send(&s_size, 1, MPI_INT, 0, TAG_DOCFILESIZE, MPI_COMM_WORLD);
                MPI_Send(results, s_size, MPI_CHAR, 0, TAG_DOCFILE, MPI_COMM_WORLD);
            }
            else
            {
                // Master fills docfile 
                std::ofstream myDocFile;
                FileName fn_tmp;
                fn_tmp.compose(prm.fn_root + "_it",iter,"doc");
                myDocFile.open (fn_tmp.c_str());
                myDocFile << " ; Headerinfo columns: rot (1), tilt (2), psi (3), Xoff (4), Yoff (5), Ref (6), Flip (7), Pmax/sumP (8), LL (9), bgmean (10), scale (11), w_robust (12)\n";

                // Master's own contribution
                myDocFile << DFo;
                int docCounter=1;
                while (docCounter < size)
                {
                    // receive in order
                    int iNumber, s_size;
                    MPI_Recv(&s_size, 1, MPI_INT, docCounter, TAG_DOCFILESIZE, MPI_COMM_WORLD, &status);
                    char results[s_size];
                    MPI_Recv(results, s_size, MPI_CHAR, docCounter, TAG_DOCFILE, MPI_COMM_WORLD, &status);
                    results[s_size]='\0';
                    myDocFile<<results ;
                    docCounter++;
                }

                //save doc_file and renumber it
                myDocFile.close();
                DFo.clear();
                DFo.read(fn_tmp);
                DFo.renum();

                // Output all intermediate files
                prm.writeOutputFiles(iter, DFo, sumw_allrefs, LL, sumcorr, conv);
            }
            MPI_Barrier(MPI_COMM_WORLD);
            
            if (converged)
            {
                if (prm.verb > 0) std::cerr << " Optimization converged!" << std::endl;
                break;
            }
            else
            {
                // reset DFo
                DFo.clear();
            }
            MPI_Barrier(MPI_COMM_WORLD);

        } // end loop iterations
	if (rank == 0)  
	    prm.writeOutputFiles(-1, DFo, sumw_allrefs, LL, sumcorr, conv);

    }
    catch (Xmipp_error XE)
    {
        if (rank == 0)
        {
            std::cout << XE;
            prm.usage();
        }
        MPI_Finalize();
        exit(1);
    }

    MPI_Finalize();
    return 0;
}
