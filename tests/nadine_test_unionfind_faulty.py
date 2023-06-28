from qsurface.main import *
from tests.variables import *
import time
from collections import defaultdict
import json
from datetime import datetime

ds = [5, 6, 7, 8, 9]
ps = [0.02]
itera = 10000

for d in ds:
    code, decoder = initialize(
        d, #size = 5 is d = 5
        "planar",
        "unionfind",
        enabled_errors=["pauli"],
        faulty_measurements=True,
        initial_states=(0, 0),
        plotting=False,
        plot_params=no_wait_param,
        step_bucket=False,
        step_cluster=False,
        step_cycle=False,
        step_peel=False,
        mp_queue=True
    )
    for p in ps:
        start = time.time()
        final_dict_failure = defaultdict(int) # stores how many times each one is correct
        final_dict_nofailure = defaultdict(int) # stores how many times each one is correct

        # run it
        for i in range(itera):
            output = run(code, decoder, iterations=1, error_rates={"p_bitflip": p, "p_bitflip_plaq": p}, decode_initial=False)
            if output['no_error'] == 1:
                final_dict_nofailure[output['phi']] += 1
            elif output['no_error'] == 0:
                final_dict_failure[output['phi']] += 1
        end = time.time()
        print('FINAL no failure dict: \n', final_dict_nofailure)
        print('FINAL failure dict: \n', final_dict_failure)

        # save it
        json_str = json.dumps(final_dict_nofailure)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        file_name = f"data_actualfaultymeas/d{d}_nofailure_p_{p}_num{itera}_{timestamp}.txt"
        file_name2 = f"data_actualfaultymeas/d{d}_failure_p_{p}_num{itera}_{timestamp}.txt"
        with open(file_name, "w") as file:
            file.write(json_str)

        json_str2 = json.dumps(final_dict_failure)
        with open(file_name2, "w") as file:
            file.write(json_str2)

        print('total time elapsed ', (end-start)/60, ' min')