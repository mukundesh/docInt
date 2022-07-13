Using docInt to extract statement information from a bank statement pdf(bank-oct-2022.pdf)

```py linenums="1"
import docint

# create a pipeline to process hdfc bank statement
hdfc_pipeline = docint.load('hdfc-bank.yml')

# pass the pdf to the pipeline
hdfc_doc = hdfc_pipeline('hdfc-oct-2022.pdf')
print(hdfc_doc.statement)

```

## Building a pipeline

A docInt pipeline in its most common form is a series of pipes (tasks)
described in a yaml file. The pipeline takes as an input a pdf file
and creates a document object and passes the document object across
the various pipes, each pipe takes a single document (or a set of
documents) and processes it and returns the document back, which is
then passed to the next pipe.

Every pipe object process the document and extracts some entities and
attches those entities to the document object and returns the
document.

Here is a sample pipline file

``` yaml 

pipeline:
  - name: gcv_recognizer
    config:
      bucket: pedia

  - name: num_marker
    config:
      x_range: [0, 0.3]
      max_number: 150

  - name: html_generator
    config:
      image_root: ../.img      
      html_root: html
      color_dict:
        nummarker: green

  - name: list_finder
    config:
      find_roman: False

  - name: list_html_generator
    component: html_generator
    config:
      image_root: ../.img      
      html_root: html
      color_dict:
        nummarker: green


```

The pipeline file has pipeline level configuration at the top, namely
`image_root` and `batch_size` followed the `pipeline:` section. The
pipeline section consists of series of pipes that are processed one
after the other.

Let's look at the first pipe `gcv_recognizer`

```
  - name: gcv_recognizer
    config:
      bucket: pedia
```

This pipe is made from the component gcv_recognizer, a component can be thought of
as the type of the pipe object, docInt comes with several components for extracting
various entities and doing other document processing tasks.

Given that this pipeline has only one instance of the component `gcv_recognizer` we
will use it as the name of the pipe. If a pipeline needs to use the same component
multiple times like `html_generator` later in the pipeline then you will have to
specify the `component` separately.

There is also a `config:` section where you can provide/override configurations of
the component, here have specified the `bucket` in the configuration. The
configurations and their default values for `gcv_recognizer` can be found at this link

### Processing multiple documents

A pipeline can process multiple documents as well as a single document. Use the method `Pipeline.pipe_all` to process multiple documents.

```py
>> import docint
>> from pathlib import Path
>> # create a pipeline to process hdfc bank statement
>> hdfc_pipeline = docint.load('hdfc-bank.yml')
>> 
>> statement_dir = Path('hdfc-statements')
>> hdfc_docs = hdfc_pipeline.pipe_all(statement_dir.glob('*.pdf'))
>> hdfc_docs[0].statement
>>
```

### Programmatically building pipeline

You don't need a yml file to configure a pipeline you can also build and configure a
pipeline through methods provided in the `Pipeline` class.


```py
>> import docint
>> 
>> # create a pipeline to process hdfc bank statement
>> small_pipeline = docint.empty()
>> 
>> small_pipeline.add_pipe('gcv_recognizer', bucket='pedia')
>> small_pipeline.add_pipe('html_gnerator', html_root='pedia')
>> hdfc_statement = small_pipeline('hdfc-oct-2022.pdf')
>>
```
