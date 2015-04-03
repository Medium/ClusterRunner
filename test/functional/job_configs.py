from test.framework.functional.fs_item import File, Directory

# These are the files that we expect to be present in every atom artifact directory.
DEFAULT_ATOM_FILES = [File('clusterrunner_command'),
                      File('clusterrunner_console_output'),
                      File('clusterrunner_exit_code'),
                      File('clusterrunner_time'), ]


class FunctionalTestJobConfig(object):
    def __init__(self, config, expected_to_fail, expected_num_subjobs,
                 expected_num_atoms,
                 expected_artifact_contents=None,
                 expected_project_dir_contents=None):
        self.config = config
        self.expected_to_fail = expected_to_fail
        self.expected_num_subjobs = expected_num_subjobs
        self.expected_num_atoms = expected_num_atoms
        self.expected_artifact_contents = expected_artifact_contents
        self.expected_project_dir_contents = expected_project_dir_contents

# This is a very basic job where each atom just creates a simple text file.
BASIC_JOB = FunctionalTestJobConfig(
    config="""

BasicJob:
    commands:
        - echo $TOKEN > $ARTIFACT_DIR/result.txt
    atomizers:
        - TOKEN: seq 0 4 | xargs -I {} echo "This is atom {}"

""",
    expected_to_fail=False,
    expected_num_subjobs=5,
    expected_num_atoms=5,
    expected_artifact_contents=[Directory('artifact_0_0', DEFAULT_ATOM_FILES +
                                          [File('result.txt',
                                                contents='This is atom 0\n')]),
                                Directory('artifact_1_0', DEFAULT_ATOM_FILES +
                                          [File('result.txt',
                                                contents='This is atom 1\n')]),
                                Directory('artifact_2_0', DEFAULT_ATOM_FILES +
                                          [File('result.txt',
                                                contents='This is atom 2\n')]),
                                Directory('artifact_3_0', DEFAULT_ATOM_FILES +
                                          [File('result.txt',
                                                contents='This is atom 3\n')]),
                                Directory('artifact_4_0', DEFAULT_ATOM_FILES +
                                          [File('result.txt',
                                                contents='This is atom 4\n')]),
                                File('results.tar.gz'), ], )

# This is a very basic job, but one of the atoms will fail with non-zero exit code.
BASIC_FAILING_JOB = FunctionalTestJobConfig(
    config="""

BasicFailingJob:
    commands:
        - if [ "$TOKEN" = "This is atom 3" ]; then exit 1; fi
        - echo $TOKEN > $ARTIFACT_DIR/result.txt
    atomizers:
        - TOKEN: seq 0 4 | xargs -I {} echo "This is atom {}"

""",
    expected_to_fail=True,
    expected_num_subjobs=5,
    expected_num_atoms=5,
    expected_artifact_contents=[Directory('artifact_0_0', DEFAULT_ATOM_FILES +
                                          [File('result.txt',
                                                contents='This is atom 0\n')]),
                                Directory('artifact_1_0', DEFAULT_ATOM_FILES +
                                          [File('result.txt',
                                                contents='This is atom 1\n')]),
                                Directory('artifact_2_0', DEFAULT_ATOM_FILES +
                                          [File('result.txt',
                                                contents='This is atom 2\n')]),
                                Directory('artifact_3_0', DEFAULT_ATOM_FILES),
                                Directory('artifact_4_0', DEFAULT_ATOM_FILES +
                                          [File('result.txt',
                                                contents='This is atom 4\n')]),
                                File('results.tar.gz'),
                                File('failures.txt',
                                     contents='artifact_3_0'), ], )

# This is a more complex job. Each step (setup_build, commands, teardown_build) depends on the previous steps. This
# config also includes short sleeps to help tease out race conditions around setup and teardown timing.
JOB_WITH_SETUP_AND_TEARDOWN = FunctionalTestJobConfig(
    config="""

JobWithSetupAndTeardown:
    setup_build:
        - echo "Doing build setup."
        - sleep 1
        - echo "setup." > $PROJECT_DIR/build_setup.txt

    commands:
        - echo "Doing subjob $SUBJOB_NUMBER."
        - sleep 1
        - MY_SUBJOB_FILE=$PROJECT_DIR/subjob_file_${SUBJOB_NUMBER}.txt
        - cp build_setup.txt $MY_SUBJOB_FILE
        - echo "subjob $SUBJOB_NUMBER." >> $MY_SUBJOB_FILE

    atomizers:
        - SUBJOB_NUMBER: seq 1 3

    teardown_build:
        - echo "Doing build teardown."
        - sleep 1
        - ALL_SUBJOB_FILES=$(ls $PROJECT_DIR/subjob_file_*.txt)
        - echo "teardown." | tee -a $ALL_SUBJOB_FILES

""",
    expected_to_fail=False,
    expected_num_subjobs=3,
    expected_num_atoms=3,
    expected_project_dir_contents=
    [File('build_setup.txt',
          contents='setup.\n'),
     File('subjob_file_1.txt',
          contents='setup.\nsubjob 1.\nteardown.\n'),
     File('subjob_file_2.txt',
          contents='setup.\nsubjob 2.\nteardown.\n'),
     File('subjob_file_3.txt',
          contents='setup.\nsubjob 3.\nteardown.\n'), ], )
