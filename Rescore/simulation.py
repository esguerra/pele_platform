import subprocess
import os
import shutil
import glob
import PELE_Platform.Utilities.Parameters.pele_env as pele
import PELE_Platform.Utilities.Helpers.constraints as ct
import PELE_Platform.constants as cs
import PELE_Platform.Utilities.Helpers.system_prep as sp
import PELE_Platform.Utilities.PPP.mut_prep4pele as ppp
import PELE_Platform.Utilities.PlopRotTemp.main as plop
import PELE_Platform.Utilities.Helpers.missing_residues as mr
import PELE_Platform.Utilities.Helpers.simulation as ad
import PELE_Platform.Utilities.Helpers.center_of_mass as cm
import PELE_Platform.Utilities.Helpers.randomize as rd
import PELE_Platform.Utilities.Helpers.helpers as hp
import PELE_Platform.Utilities.Helpers.metrics as mt
import PELE_Platform.Utilities.Helpers.external_files as ext
import PELE_Platform.Utilities.Helpers.solventOBCParamsGenerator as obc



def run_adaptive(args):
    # Build Folders and Logging and env variable that will containt
    #all main  attributes of the simulation
    env = pele.EnviroBuilder.build_env(args)

    if args.restart == "all":

        # Build System
        env.logger.info("Checking {} system for Pele".format(args.residue))
        syst = sp.SystemBuilder.build_system(args.system, args.mae_lig, args.residue, env.pele_dir)
        
        ########Choose your own input####################
        if args.input:
            env.inputs_simulation = []
            for input in env.input:
                input_path  = os.path.join(env.pele_dir, os.path.basename(input))
                shutil.copy(input, input_path)
                input_proc = ppp.main(input_path, env.pele_dir, output_pdb=["" , ],
                                charge_terminals=args.charge_ter, no_gaps_ter=args.gaps_ter)[0]
                env.inputs_simulation.append(input_proc)
                hp.silentremove([input_path])
            env.adap_ex_input = ", ".join(['"' + input +  '"' for input in env.inputs_simulation])
        elif args.full or args.randomize:
            ligand_positions = rd.randomize_starting_position(env.ligand_ref, "input_ligand.pdb", env.residue, env.receptor, None, None, env)
            inputs = rd.join(env.receptor, ligand_positions, env)
            hp.silentremove(ligand_positions)
            #Parsing input for errors and saving them as inputs
            env.adap_ex_input = ", ".join([ '"' + ppp.main(input, env.pele_dir, output_pdb=["" , ], 
                charge_terminals=args.charge_ter, no_gaps_ter=args.gaps_ter)[0] + '"' for input in inputs ])
            hp.silentremove(inputs)

        ##########Prepare System################
        if env.no_ppp:
            env.adap_ex_input = system_fix = syst.system
            missing_residues = []
            gaps = {}
            metals = {}
            env.constraints = ct.retrieve_constraints(system_fix, gaps, metals)
            shutil.copy(env.adap_ex_input, env.pele_dir)
        else:
            system_fix, missing_residues, gaps, metals, env.constraints = ppp.main(syst.system, env.pele_dir, charge_terminals=args.charge_ter, no_gaps_ter=args.gaps_ter, mid_chain_nonstd_residue=env.nonstandard, skip=env.skip_prep)
        env.logger.info(cs.SYSTEM.format(system_fix, missing_residues, gaps, metals))

        ############Build metrics##################
        metrics = mt.Metrics_Builder(env.system_fix)
        if env.atom_dist:
            metrics.distance_to_atom(args.atom_dist)
        env.metrics = "\n".join(metrics.get_metrics()) if metrics.get_metrics() else None

        ############3Parametrize Ligand###############3
        if not env.external_template and not env.external_rotamers:
            env.logger.info("Creating template for residue {}".format(args.residue))
            plop.parametrize_miss_residues(args, env, syst)
            env.logger.info("Template {}z created".format(args.residue.lower()))
        else:
            cmd_to_move_template = "cp {} {}".format(env.external_template,  env.template_folder)
            subprocess.call(cmd_to_move_template.split())
            cmd_to_move_rotamer_file = "cp {} {}".format(env.external_rotamers, env.rotamers_folder)
            subprocess.call(cmd_to_move_rotamer_file.split())



        ###########Parametrize missing residues#################
        for res, __, _ in missing_residues:
            if res != args.residue:
                env.logger.info("Creating template for residue {}".format(res))
                mr.create_template(system_fix, res, env.pele_dir, args.forcefield)
                env.logger.info("Template {}z created".format(res))

        #########Parametrize solvent parameters if need it##############
        if env.solvent == "OBC":
            shutil.copy(env.obc_tmp, env.obc_file)
            for template in glob.glob(os.path.join(env.template_folder, "*")):
                obc.main(template, env.obc_file)


        #################3Set Box###################3
        if not env.box_center:
            env.box_center = cm.center_of_mass(env.ligand_ref)
            env.logger.info("Box {} created".format(env.box_center))
        
        ############Fill in Simulation Templates############
        env.logger.info("Running Simulation")
        if env.adapt_conf:
            ext.external_adaptive_file(env)
        if env.confile:
            ext.external_pele_file(env)
        adaptive = ad.SimulationBuilder(env.ad_ex_temp, env.pele_exit_temp, env)
        adaptive.run()
        
    return env
