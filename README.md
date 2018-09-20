# Autonomic-Intelligence-Engine (AIE)



The **Autonomic-Intelligence-Engine (AIE)** hosts and currates the machine learning based intelligence of the **SELFNET framework**. 

Whereas the TAL-Engine is focused on fast, realtime handling of known Symptoms from the Monitoring/Aggregation Layer, the AIE strives to learn and thus evolve the capabilities of the overall system over time.  One example is the definition of new Symptoms in the Monitoring/Aggregation Layer (as shown in the SP-UC) with the corresponding reaction (TAL-Script) in the TAL-Engine. For the Symptom generation NeuroEvolution of Augmented Topologies (NEAT) is being used to evolve a neural network for classification which is translated and updated as a new Symptom into the Selfnet framework. This enables the dynamic creation of new symptoms which can now processed in the TAL-Engine in realtime upon trigger.

ML enhanced diagnostics, which might not be feasible in other layers due to the overall system dependency are possible in AIE. This is shown in the scope of the SH-UC where an VNF profiling based on autoencoders is being performed. 



## Installation

### Requirements (AIE) [Machine Learning functionality]

The AIE focusing on machine learning has it's core functionallity written in python. 

```
Required Python Packages:
- jsonschema
- pyyaml
- numpy
- kafka
- python-monascaclient
- cassandra-driver
- for tests:
  - matplotlib
  - tkinter (ubuntu: python3-tk package)
```

**Machine Learning requirements**

For the machine learning logic the necessary **NVIDIA Cuda Toolkit** ( here v.9.0 was used) and matching **cudnn** should be installed and set up. Guides can be found here for 

[Windows]: https://docs.nvidia.com/cuda/cuda-installation-guide-microsoft-windows/index.html

and 

[Linux]: https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html



In case that the other components of the Selfnet Framework are skipped, make sure to indicate so in the YAML-config according to the provided shema. 



### Dependencies (Components) [Full functionality]

As AIE is tightly linked to the TAL-Engine and the underlying Monitoring/Aggregation layers it is necessary that the components in those layers are set up before hand. At the minimum following components are necessary to be present and set up.

------

 [ **Component**  - used for AIE functionality ]

1. **TAL-Engine** - TAL-Script creation, update, activation/deactivation
2. **Aggregation Layer**
   1. **Aggregation-Engine**  - Aggregation Rule creation, update
   2. **CEP-Engine**  - Generates input for ML-modules
   3. **Threshold-Engine**  - Symptom creation, update
3. **Monitoring Layer** - (Input Data)
   1. Sensors (FMA, Zabbix, ...)
   2. **Raw-Data-Loader** 
   3. Monitoring Database (**Cassandra**)

------



## Usage

**Configuration**

The YAML-config files allow to define environment variables (IPs/Ports of other components) and fallback values in case of tests and dry-runs (local data dump files). 



**Run**

```
./py.py
```





# License

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at <http://www.apache.org/licenses/LICENSE-2.0> Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.



# Acknowledge

Software Supported by H2020 5G-PPP SELFNET PROJECT with project ID H2020-ICT-2014-2;